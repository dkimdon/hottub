# frozen_string_literal: true

# Tests for the Ruby operator.  No tub and no network needed.
#
#     ruby test_operator.rb
#
# Requires the balboa_worldwide_app gem.  To test against a checkout instead:
#
#     ruby -I ../../balboa_worldwide_app/lib test_operator.rb
#
# These mirror ../operator/tests/test_controller.py.

require 'minitest/autorun'
require 'socket'
require 'tmpdir'

require_relative 'hottub_operator'

OFF = { 'heating_mode' => 'rest', 'temperature_range' => 'low', 'set_temperature' => 50 }.freeze

def on(temperature)
  { 'heating_mode' => 'ready', 'temperature_range' => 'high', 'set_temperature' => temperature }
end

# Stands in for a BWA::Client connected to a tub.  Like the real tub, it keeps
# a separate set temperature for each range and ignores out-of-range requests.
class FakeSpa
  attr_accessor :heating_mode, :temperature_range, :temperature_scale, :current_temperature, :silent
  attr_writer :set_temperature # what the panel does; the method below is what the client sends

  def initialize
    @heating_mode = :ready
    @temperature_range = :high
    @set_temperature = 102
    @temperature_scale = :fahrenheit
    @current_temperature = 100
    @silent = false
  end

  def poll
    sleep if @silent # until the caller's timeout fires
    status = BWA::Messages::Status.new
    status.heating_mode = @heating_mode
    status.temperature_range = @temperature_range
    status.instance_variable_set(:@temperature_scale, @temperature_scale)
    status.set_temperature = @set_temperature
    status.current_temperature = @current_temperature
    status.heating = (@heating_mode == :ready)
    status
  end

  def toggle_heating_mode
    @heating_mode = @heating_mode == :ready ? :rest : :ready
  end

  def toggle_temperature_range
    if @temperature_range == :high
      @temperature_range = :low
      @set_temperature = 60
    else
      @temperature_range = :high
      @set_temperature = 100
    end
  end

  def set_temperature(value)
    limits = @temperature_range == :high ? (80..106) : (50..80)
    @set_temperature = value if limits.cover?(value)
  end

  def controls
    HottubOperator.control_state(poll)
  end
end

# Behaves like the real API's operator endpoints, in memory.
class FakeApi
  attr_accessor :desired, :version, :source, :reports, :fail_reports, :ui_change_during_report

  def initialize(desired = nil)
    @desired = desired
    @version = desired.nil? ? nil : 1
    @source = desired.nil? ? nil : 'ui'
    @reports = []
    @fail_reports = false
    @ui_change_during_report = nil
  end

  def ui_sets(desired)
    @desired = desired
    @source = 'ui'
    @version = (@version || 0) + 1
  end

  def get_desired
    { 'desired' => @desired, 'desired_version' => @version }
  end

  def report(tub, panel_change = false, desired_version = nil)
    raise HottubOperator::ApiError, 'report failed' if @fail_reports
    @reports << tub
    unless @ui_change_during_report.nil?
      ui_sets(@ui_change_during_report)
      @ui_change_during_report = nil
    end
    adopted = false
    if panel_change && desired_version == @version
      @desired = {
        'heating_mode' => tub['heating_mode'] == 'ready' ? 'ready' : 'rest',
        'temperature_range' => tub['temperature_range'],
        'set_temperature' => tub['set_temperature']
      }
      @source = 'panel'
      @version = (@version || 0) + 1
      adopted = true
    end
    { 'adopted' => adopted, 'desired' => @desired, 'desired_version' => @version }
  end
end

class OperatorTest < Minitest::Test
  def setup
    @tub = FakeSpa.new
    @dir = Dir.mktmpdir
    @state = HottubOperator::StateFile.new(File.join(@dir, 'state.json'))
    @real_stdout = $stdout
    $stdout = StringIO.new # keep the operator's log out of the test output
  end

  def teardown
    $stdout = @real_stdout
    FileUtils.remove_entry(@dir)
  end

  def cycle(api, report_only = false)
    HottubOperator.run_cycle(api, -> { @tub }, @state, report_only)
  end
end

class TestApplyingDesiredState < OperatorTest
  def test_in_step_changes_nothing
    api = FakeApi.new(on(102))
    assert_equal 'in-step', cycle(api)
    assert_equal on(102), @tub.controls
    assert_equal 100, api.reports.last['current_temperature']
  end

  def test_changes_set_temperature
    [104, 105, 106].each do |temperature|
      api = FakeApi.new(on(temperature))
      assert_equal 'changed', cycle(api)
      assert_equal on(temperature), @tub.controls
      assert_equal temperature, api.reports.last['set_temperature']
    end
  end

  def test_turns_off_and_back_on
    api = FakeApi.new(OFF)
    assert_equal 'changed', cycle(api)
    assert_equal OFF, @tub.controls

    api.ui_sets(on(105))
    assert_equal 'changed', cycle(api)
    assert_equal on(105), @tub.controls
    assert_equal 'ui', api.source
  end

  def test_ready_in_rest_counts_as_rest
    api = FakeApi.new(OFF)
    cycle(api)
    @tub.heating_mode = :ready_in_rest # someone turned the jets on
    assert_equal 'in-step', cycle(api)
    assert_equal 'ui', api.source
    assert_equal 'ready_in_rest', api.reports.last['heating_mode']
  end

  def test_rejected_change_is_retried_not_mistaken_for_panel
    HottubOperator.send(:remove_const, :STATUS_TIMEOUT)
    HottubOperator.const_set(:STATUS_TIMEOUT, 0.2)
    api = FakeApi.new(on(104))
    cycle(api)
    api.ui_sets(on(120)) # outside the tub's range; it ignores the request
    assert_equal 'change-failed', cycle(api)
    assert_equal on(104), @tub.controls
    assert_equal 'change-failed', cycle(api)
    assert_equal on(120), api.desired
    assert_equal 'ui', api.source
  ensure
    HottubOperator.send(:remove_const, :STATUS_TIMEOUT)
    HottubOperator.const_set(:STATUS_TIMEOUT, 5)
  end
end

class TestPanelChanges < OperatorTest
  def test_panel_change_is_adopted_not_undone
    api = FakeApi.new(on(104))
    cycle(api)
    @tub.set_temperature = 100 # pressed "down" at the tub
    assert_equal 'panel-change', cycle(api)
    assert_equal on(100), @tub.controls
    assert_equal on(100), api.desired
    assert_equal 'panel', api.source
    assert_equal 'in-step', cycle(api)
    assert_equal on(100), @tub.controls
  end

  def test_ui_change_after_panel_change_wins
    api = FakeApi.new(on(104))
    cycle(api)
    @tub.set_temperature = 100
    cycle(api)
    api.ui_sets(on(106))
    assert_equal 'changed', cycle(api)
    assert_equal on(106), @tub.controls
    assert_equal 'ui', api.source
  end

  def test_panel_change_after_ui_change_wins
    api = FakeApi.new(on(104))
    cycle(api)
    api.ui_sets(on(106))
    cycle(api)
    @tub.heating_mode = :rest # switched to rest at the tub
    assert_equal 'panel-change', cycle(api)
    assert_equal :rest, @tub.heating_mode
    assert_equal 'rest', api.desired['heating_mode']
  end

  def test_ui_change_racing_a_panel_report_wins
    api = FakeApi.new(on(104))
    cycle(api)
    @tub.set_temperature = 100
    # A user picks 106 after the operator read the desired state but before
    # its panel report arrives.
    api.ui_change_during_report = on(106)
    assert_equal 'changed', cycle(api)
    assert_equal on(106), @tub.controls
    assert_equal on(106), api.desired
    assert_equal 'ui', api.source
  end

  def test_new_system_starts_from_the_tub
    api = FakeApi.new(nil)
    assert_equal 'panel-change', cycle(api)
    assert_equal on(102), api.desired
    assert_equal on(102), @tub.controls
  end

  def test_lost_state_file_means_cloud_wins
    api = FakeApi.new(on(104))
    @tub.set_temperature = 100
    assert_equal 'changed', cycle(api)
    assert_equal on(104), @tub.controls
  end

  def test_failed_report_after_our_change_is_not_a_panel_change
    api = FakeApi.new(on(104))
    cycle(api)
    api.ui_sets(on(106))
    api.fail_reports = true
    assert_raises(HottubOperator::ApiError) { cycle(api) }
    assert_equal on(106), @tub.controls
    api.fail_reports = false
    assert_equal 'in-step', cycle(api)
    assert_equal 'ui', api.source
  end
end

class TestReportOnly < OperatorTest
  def test_never_changes_tub_or_desired_state
    api = FakeApi.new(on(106))
    assert_equal 'reported', cycle(api, true)
    @tub.set_temperature = 100
    assert_equal 'reported', cycle(api, true)
    assert_equal on(100), @tub.controls
    assert_equal on(106), api.desired
    assert_equal 100, api.reports.last['set_temperature']
  end
end

class TestFailures < OperatorTest
  def test_tub_unreachable_is_reported
    api = FakeApi.new(on(104))
    refuse = -> { raise Errno::ECONNREFUSED }
    assert_equal 'tub-unreachable', HottubOperator.run_cycle(api, refuse, @state)
    assert_equal [nil], api.reports
  end

  def test_silent_tub_is_reported_unreachable
    HottubOperator.send(:remove_const, :STATUS_TIMEOUT)
    HottubOperator.const_set(:STATUS_TIMEOUT, 0.2)
    api = FakeApi.new(on(104))
    @tub.silent = true
    assert_equal 'tub-unreachable', cycle(api)
    assert_equal [nil], api.reports
  ensure
    HottubOperator.send(:remove_const, :STATUS_TIMEOUT)
    HottubOperator.const_set(:STATUS_TIMEOUT, 5)
  end

  def test_celsius_tub_is_left_alone
    api = FakeApi.new(on(104))
    @tub.temperature_scale = :celsius
    @tub.set_temperature = 38
    assert_equal 'celsius', cycle(api)
    assert_equal 38, @tub.controls['set_temperature']
  end

  def test_api_down_leaves_tub_alone
    api = FakeApi.new(on(106))
    def api.get_desired
      raise HottubOperator::ApiError, 'down'
    end
    assert_raises(HottubOperator::ApiError) { cycle(api) }
    assert_equal on(102), @tub.controls
  end

  def test_state_file_survives_corruption
    File.write(File.join(@dir, 'state.json'), '{not json')
    assert_equal({}, @state.load)
  end
end

# The real bwa client against the bwa library's own simulated tub.
class TestWithBwaLibrary < OperatorTest
  def test_cycle_over_a_real_connection
    HottubOperator.send(:remove_const, :STATUS_TIMEOUT)
    HottubOperator.const_set(:STATUS_TIMEOUT, 3)
    require 'bwa/server'
    port = TCPServer.open('127.0.0.1', 0) { |s| s.addr[1] }
    server = BWA::Server.new(port)
    thread = Thread.new { server.run }
    # 'localhost', not 127.0.0.1: the library's server may listen on IPv6 only.
    connect = -> { BWA::Client.new('localhost', port) }

    # The simulated tub starts at ready / high / 100.
    api = FakeApi.new(on(105))
    assert_equal 'changed', HottubOperator.run_cycle(api, connect, @state)
    assert_equal 105, api.reports.last['set_temperature']
    assert_equal 'ready', api.reports.last['heating_mode']
  ensure
    thread.kill if thread
    HottubOperator.send(:remove_const, :STATUS_TIMEOUT)
    HottubOperator.const_set(:STATUS_TIMEOUT, 5)
  end
end

# The Api class over real HTTP, against a one-request local server.
class TestApi < Minitest::Test
  def serve(status_line, body)
    server = TCPServer.new('127.0.0.1', 0)
    received = Queue.new
    Thread.new do
      client = server.accept
      head = +''
      head << client.readpartial(4096) until head.include?("\r\n\r\n")
      length = head[/content-length: (\d+)/i, 1].to_i
      sent = head.split("\r\n\r\n", 2)[1].to_s
      sent << client.readpartial(4096) while sent.bytesize < length
      received << [head, sent]
      client.write("HTTP/1.1 #{status_line}\r\nContent-Type: application/json\r\n" \
                   "Content-Length: #{body.bytesize}\r\nConnection: close\r\n\r\n#{body}")
      client.close
      server.close
    end
    ["http://127.0.0.1:#{server.addr[1]}", received]
  end

  def test_get_desired_sends_the_key
    url, received = serve('200 OK', '{"desired": null, "desired_version": null}')
    answer = HottubOperator::Api.new(url, 'secret-key').get_desired
    assert_equal({ 'desired' => nil, 'desired_version' => nil }, answer)
    head, = received.pop
    assert_match %r{\AGET /operator/desired }, head
    assert_match(/^x-operator-key: secret-key\r$/i, head)
  end

  def test_report_sends_json
    url, received = serve('200 OK', '{"adopted": true, "desired": null, "desired_version": 3}')
    answer = HottubOperator::Api.new(url, 'k').report({ 'set_temperature' => 104 }, true, 2)
    assert_equal true, answer['adopted']
    head, body = received.pop
    assert_match %r{\APUT /operator/report }, head
    assert_equal({ 'tub' => { 'set_temperature' => 104 }, 'panel_change' => true, 'desired_version' => 2 },
                 JSON.parse(body))
  end

  def test_http_error_becomes_api_error
    url, = serve('401 Unauthorized', '{"error": "Invalid operator key"}')
    error = assert_raises(HottubOperator::ApiError) { HottubOperator::Api.new(url, 'bad').get_desired }
    assert_match(/HTTP 401/, error.message)
  end

  def test_unreachable_api_becomes_api_error
    port = TCPServer.open('127.0.0.1', 0) { |s| s.addr[1] }
    assert_raises(HottubOperator::ApiError) do
      HottubOperator::Api.new("http://127.0.0.1:#{port}", 'k', 2).get_desired
    end
  end

  def test_plain_http_is_refused_for_real_hosts
    assert_raises(ArgumentError) { HottubOperator::Api.new('http://example.com', 'k') }
    HottubOperator::Api.new('https://example.com/', 'k')
  end
end

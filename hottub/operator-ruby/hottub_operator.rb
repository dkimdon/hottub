#!/usr/bin/env ruby
# frozen_string_literal: true

# Hot tub operator (Ruby version) -- runs on the tub's network and keeps the
# tub and the cloud in step.  Each run does ONE control cycle and exits;
# run-termux.sh calls it every two minutes.
#
#     ruby hottub_operator.rb                # one cycle
#     ruby hottub_operator.rb --report-only  # never change the tub
#
# Configuration comes from environment variables:
#
#     HOTTUB_API_URL        required   base URL of the API (https://...)
#     HOTTUB_OPERATOR_KEY   required   the operator's shared key
#     HOTTUB_SPA_IP         optional   the tub's IP address; found by UDP
#                                      discovery if not set
#     HOTTUB_STATE_FILE     optional   default: operator-state.json next to
#                                      this file
#
# It needs the balboa_worldwide_app gem (the "bwa" library) that the old
# operator already uses, and nothing else beyond Ruby's standard library.
#
# What a cycle does:
#
#   1. Ask the API what the tub should be doing (the "desired" controls).
#   2. Connect to the tub and read what it is doing.
#   3. If the tub's controls differ from how we left them last cycle, someone
#      used the front panel.  Report that; it becomes the new desired state --
#      unless a user changed the setpoint in the web UI in the same moment,
#      in which case the API tells us the UI's change stands.
#   4. Otherwise, if the tub differs from the desired controls, change the tub.
#   5. Report the tub's temperature and state.
#
# "Controls" are the three things this system manages:
#
#     { "heating_mode" => "ready" | "rest",
#       "temperature_range" => "high" | "low",
#       "set_temperature" => 104 }
#
# The most recent change wins, whether it came from the web UI or the panel.
#
# This is a port of ../operator/controller.py; keep the two in step.

require 'json'
require 'net/http'
require 'timeout'
require 'uri'

require 'bwa/client'
require 'bwa/discovery'

module HottubOperator
  # The API could not be reached or refused the request.
  class ApiError < StandardError; end

  # The tub did not answer, or stopped answering part-way through.
  class TubUnreachable < StandardError; end

  CONNECT_TIMEOUT = 10
  # How long to wait for a status, or for the tub to confirm a change.
  STATUS_TIMEOUT = 5

  def self.log(message)
    puts "#{Time.now.strftime('%Y-%m-%d %H:%M:%S')} #{message}"
    $stdout.flush
  end

  # ------------------------------------------------------------------
  # The API
  # ------------------------------------------------------------------

  class Api
    def initialize(base_url, operator_key, timeout = 15)
      @base = URI.parse(base_url.sub(%r{/+\z}, ''))
      local = %w[localhost 127.0.0.1].include?(@base.host)
      # The operator key travels in a header; never send it in the clear.
      unless @base.scheme == 'https' || (@base.scheme == 'http' && local)
        raise ArgumentError, 'The API URL must start with https://'
      end
      @operator_key = operator_key
      @timeout = timeout
    end

    # Returns { "desired" => {...} or nil, "desired_version" => Integer or nil }
    def get_desired
      request(Net::HTTP::Get, '/operator/desired')
    end

    # Report the tub's state (nil = could not reach the tub).
    # Returns { "adopted" => bool, "desired" => ..., "desired_version" => ... }
    def report(tub, panel_change = false, desired_version = nil)
      body = { 'tub' => tub }
      if panel_change
        body['panel_change'] = true
        body['desired_version'] = desired_version
      end
      request(Net::HTTP::Put, '/operator/report', body)
    end

    private

    def request(verb, path, body = nil)
      http = Net::HTTP.new(@base.host, @base.port)
      http.use_ssl = (@base.scheme == 'https')
      http.open_timeout = @timeout
      http.read_timeout = @timeout

      req = verb.new(@base.path + path)
      req['X-Operator-Key'] = @operator_key
      req['Content-Type'] = 'application/json'
      req['User-Agent'] = 'hottub-operator-ruby'
      req.body = JSON.generate(body) unless body.nil?

      response = http.request(req)
      unless response.is_a?(Net::HTTPSuccess)
        raise ApiError, "#{req.method} #{path} failed: HTTP #{response.code} #{response.body.to_s[0, 300]}"
      end
      JSON.parse(response.body)
    rescue ApiError
      raise
    rescue StandardError, Timeout::Error => e
      raise ApiError, "#{verb::METHOD} #{path} failed: #{e.class}: #{e.message}"
    end
  end

  # ------------------------------------------------------------------
  # State kept between cycles
  # ------------------------------------------------------------------

  # Remembers how we last left the tub's controls, and where the tub was.
  class StateFile
    def initialize(path)
      @path = path
    end

    def load
      data = JSON.parse(File.read(@path))
      data.is_a?(Hash) ? data : {}
    rescue StandardError
      {}
    end

    def save(data)
      tmp = "#{@path}.tmp"
      File.write(tmp, JSON.generate(data))
      File.rename(tmp, @path)
    end
  end

  # ------------------------------------------------------------------
  # Talking to the tub
  # ------------------------------------------------------------------

  # The tub's controls, as compared against the desired state.
  def self.control_state(status)
    {
      # "Ready in rest" is rest mode with the jets temporarily on; it goes
      # back to rest by itself, so it is not a change anyone asked for.
      'heating_mode' => status.heating_mode == :ready ? 'ready' : 'rest',
      'temperature_range' => status.temperature_range.to_s,
      'set_temperature' => status.set_temperature.to_i
    }
  end

  # What we tell the API about the tub.
  def self.tub_report(status)
    {
      'current_temperature' => status.current_temperature,
      'set_temperature' => status.set_temperature.to_i,
      'heating_mode' => status.heating_mode.to_s,
      'temperature_range' => status.temperature_range.to_s,
      'heating' => status.heating ? true : false
    }
  end

  # Return the next status the tub sends for which the block is true (any
  # status if no block is given), or nil if none arrives in time.
  def self.wait_for_status(spa, seconds = STATUS_TIMEOUT)
    Timeout.timeout(seconds) do
      loop do
        begin
          message = spa.poll
        rescue BWA::InvalidMessage
          next
        end
        next unless message.is_a?(BWA::Messages::Status)
        return message if !block_given? || yield(message)
      end
    end
  rescue Timeout::Error
    nil
  rescue IOError, SystemCallError, NoMethodError => e
    # NoMethodError is how the bwa library reports a closed connection.
    raise TubUnreachable, "lost the connection to the tub (#{e.class})"
  end

  def self.read_status(spa)
    wait_for_status(spa) || raise(TubUnreachable, 'connected, but the tub sent no status')
  end

  # Change the tub's controls to `desired`; return the tub's status afterwards.
  #
  # Order matters: the tub only accepts a set temperature that lies inside
  # its current range, so the range is changed first.
  def self.apply(spa, status, desired)
    change = lambda do |description, action, confirmed|
      log "  #{description}"
      action.call
      # If the change is not confirmed, carry on with a fresh reading.
      status = wait_for_status(spa, &confirmed) || read_status(spa)
    end

    if control_state(status)['temperature_range'] != desired['temperature_range']
      change.call("temperature range -> #{desired['temperature_range']}",
                  -> { spa.toggle_temperature_range },
                  ->(s) { s.temperature_range.to_s == desired['temperature_range'] })
    end

    if control_state(status)['set_temperature'] != desired['set_temperature']
      change.call("set temperature -> #{desired['set_temperature']}",
                  -> { spa.set_temperature(desired['set_temperature'].to_i) },
                  ->(s) { s.set_temperature.to_i == desired['set_temperature'] })
    end

    if control_state(status)['heating_mode'] != desired['heating_mode']
      change.call("heating mode -> #{desired['heating_mode']}",
                  -> { spa.toggle_heating_mode },
                  ->(s) { control_state(s)['heating_mode'] == desired['heating_mode'] })
    end

    status
  end

  # ------------------------------------------------------------------
  # One control cycle
  # ------------------------------------------------------------------

  # Run one cycle and return a one-word outcome for the log.
  #
  #   api      an Api
  #   connect  a callable returning a connected BWA::Client
  #   state    a StateFile
  #
  # In report-only mode the tub is never changed and nothing it does is
  # treated as a panel change; use it to run alongside another controller.
  #
  # Raises ApiError if the API cannot be reached.
  def self.run_cycle(api, connect, state, report_only = false)
    answer = api.get_desired
    desired = answer['desired']
    version = answer['desired_version']

    spa = nil
    begin
      spa = connect.call
      status = read_status(spa)

      if status.temperature_scale != :fahrenheit
        # Everything here assumes Fahrenheit; do not guess.
        log 'Tub is set to Celsius; not controlling it'
        api.report(nil)
        return 'celsius'
      end

      tub = control_state(status)
      if report_only
        api.report(tub_report(status))
        return 'reported'
      end

      saved = state.load
      last = saved['controls']

      # No desired state at all means a brand new system: start from
      # whatever the tub is doing now.
      if desired.nil? || (!last.nil? && tub != last)
        log "Tub controls changed at the panel: #{last.inspect} -> #{tub.inspect}"
        answer = api.report(tub_report(status), true, version)
        if answer['adopted']
          state.save(saved.merge('controls' => tub))
          return 'panel-change'
        end
        log 'A newer change was made in the web UI; it takes priority'
        desired = answer['desired']
      end

      outcome = 'in-step'
      if tub != desired
        log "Changing tub controls: #{tub.inspect} -> #{desired.inspect}"
        status = apply(spa, status, desired)
        tub = control_state(status)
        if tub == desired
          outcome = 'changed'
        else
          outcome = 'change-failed'
          log "Tub did not accept the change; it is at #{tub.inspect}"
        end
      end

      # Save before reporting: if the report fails, the next cycle must not
      # mistake our own change for someone using the panel.
      state.save(saved.merge('controls' => tub))
      api.report(tub_report(status))
      outcome
    rescue TubUnreachable, IOError, SystemCallError, SocketError, Timeout::Error => e
      log "Could not talk to the tub: #{e.class}: #{e.message}"
      api.report(nil)
      'tub-unreachable'
    ensure
      close(spa)
    end
  end

  def self.close(spa)
    socket = spa && spa.instance_variable_get(:@socket)
    socket.close if socket && !socket.closed?
  rescue StandardError
    nil
  end

  # Returns a callable that locates the tub and connects to it.
  def self.make_connect(state, fixed_ip)
    lambda do
      ip = fixed_ip
      ip ||= begin
        found = BWA::Discovery.discover(5)
        found.empty? ? nil : found.keys.first
      end

      saved = state.load
      if ip.nil?
        # Discovery is a UDP broadcast and is sometimes missed; the tub rarely
        # changes address, so try where it was last time.
        ip = saved['spa_ip']
        raise TubUnreachable, 'tub not found on the network' if ip.nil?
        log "Discovery found nothing; trying last known address #{ip}"
      elsif saved['spa_ip'] != ip
        state.save(saved.merge('spa_ip' => ip))
      end

      Timeout.timeout(CONNECT_TIMEOUT) { BWA::Client.new(ip) }
    end
  end

  def self.main(argv)
    report_only = argv.include?('--report-only')
    unknown = argv - ['--report-only']
    abort "Unknown argument: #{unknown.first}" unless unknown.empty?

    url = ENV['HOTTUB_API_URL'] or abort 'Environment variable HOTTUB_API_URL is not set'
    key = ENV['HOTTUB_OPERATOR_KEY'] or abort 'Environment variable HOTTUB_OPERATOR_KEY is not set'
    begin
      api = Api.new(url, key)
    rescue ArgumentError, URI::InvalidURIError => e
      abort e.message
    end

    state = StateFile.new(ENV['HOTTUB_STATE_FILE'] || File.join(__dir__, 'operator-state.json'))
    connect = make_connect(state, ENV['HOTTUB_SPA_IP'])

    begin
      outcome = run_cycle(api, connect, state, report_only)
      log "Cycle finished: #{outcome}#{report_only ? ' (report only)' : ''}"
    rescue ApiError => e
      log "Could not talk to the API: #{e.message}"
      exit 1
    end
  end
end

HottubOperator.main(ARGV) if $PROGRAM_NAME == __FILE__

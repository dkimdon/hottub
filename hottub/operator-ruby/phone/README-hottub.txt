HOT TUB OPERATOR ON THIS PHONE
==============================

This phone runs the program that connects the hot tub to the web app
(the "operator").  It checks the tub and the web app every two minutes.

Open Termux and type one of these, then press Enter:

    ./start     start the operator (do this after the phone restarts)
    ./status    is it running? what did it do last?
    ./stop      stop it

Starting it again when it is already running does no harm.

After the phone restarts, nothing runs until you type ./start
(the tub is not controlled and is not turned off at midnight until then).


More detail
-----------

  Watch it live:      screen -r hottub
                      (leave it running with Ctrl-a then d)
  Full log:           ~/hottub-operator.log
  Settings:           ~/hottub-operator.env
                      (which web app to report to, and its key:
                       keep this file private)
  Program:            ~/hottub-operator/

Only one program may control the tub.  The old one ran in a screen
session called "hottubloop"; ./start refuses to run while it is.

./start also starts the SSH server, so the phone can be reached from a
computer with:   ssh -p 8022 u0_a1107@10.0.0.44

These files come from hottub/operator-ruby/phone/ in the hottub
repository; change them there and copy them here.

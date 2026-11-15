

* Introduction

I want to rewrite this hottub application system completely. This
system has been running for years very well and is used by about a dozen users.
However, the underlying libraries are old and my attempts to update it and add
a few new features have not been successful.  In general, I need this to be
simpler and easier to maintain.  This will never be more than a small
application used by a dozen or so users.  I will give you an overview of the
changes I am thinking of.  I want you to examine the sources files here and ask
me clarifying questions to make sure you understand what I want you to do.

* System Overview

The software here consists of two main components.

The first component is the Hottub UI.  The HotTub UI is a web app that users
interact with.  The users set desired temperature for the tub and view current
temperature setting (desired temperature) and state (the actual current
temperature of the water, the state of the tub meaning heating or at rest, etc.).

The second component is the Hottub Operator.  The Hottub Operator runs on the
same wireless network as the hot tub and also communicates with AWS over
the Internet.  The Hottub Operator runs a control loop that interfaces directly
with the tub to configure set points and read status.

** HotTub UI

All the software for the Hottub UI is under the hottub-app/ directory.  What
follows is an overview of the software in the subdirectories of hottub-app/.

app/ - This is the React frontend and the client side API implementation used
by the frontend.  The frontend provides a simple user interface that is one of
the most important features of the application.  Users login with a username
and password.  Then, once logged in a set of radio buttons allow us to set the
tub to any temperature between 102 and 106.  Users can also turn the tub off.
There are also status messages that show, for example:

- the current set point
- who made the last change (though that part is broken now, always says 'unknown')
- the time the actual temperature of the physical tub was last measured
- and a warning if it has been a long time since the tub was last contacted by the operator

aws/ - this is the AWS Cloudformation stack that manages the cloud resources.
There is also small administrative tool that I use to add new users and set
passwords, etc. 

hottub-mysql-dao/ mysql-lambda/ - these two directories contain a failed
attempt at adding a new feature.  I think they are used in some places still
but none of the associated features are working correctly.  Any references to these directories should be removed and these directories themselves should be removed.

lambda/ - This is the lambda function that the application uses right now to
make changes to the AWS IOT configuration in response to user requests that
come in from the Hottub UI and then AWS Appsync.

react-ui-thermometer/ - this is a thermometer component that is part of the Web
UI. 


** Hottub Operator

See the balboa_worldwide_app/ directory.  The main application logic is in
balboa_worldwide_app/bin/bwa_aws_iot_thing.  bwa_aws_iot_thing is periodically
invoked by a while loop in ./balboa_worldwide_app/termux-loop.sh.
termux-loop.sh runs forever.

The operator checks AWS for the desired set point (either 'off' or a
temperature between 102 and 106 degress), changes the set point of the
physical tub if necessary and reports back the current temperature to AWS.

The operator also always turns the tub off around midnight.

The operator attempts to not interfere with any changes that users made to the
tub with the physical buttons on the front of the tub.

This program depends on a library in balboa_worldwide_app/lib/ that does the
actual communication with the tub.

Sometimes the operator is unable to contact the tub for hours.  I suspect it is
the hottub's wifi module that stops working. It always recovers on its own.  I
haven't found a way of helping it recover faster and I don't understand why
sometimes the operator cannot communicate with the hottub.

* What I Want To Keep The Same

There are a number of things that I am happy with.

I want to keep using AWS Cognito for user authentication.

I want to keep using AWS Lambda for server side compute.

I want to keep using React for the UI.

I want to keep managing all AWS resource with Cloudformation.  I want to
continue to use declarative infrastructure, infrastructure as code principles.

* Desired Changes

I want to use the latest stable and secure versions of all libraries. I want
to adhere to software best practices.

I want you to rewrite this application.  I created a new directory (hottub/).
hottub/ is a new git repository where I want the Hotub UI and the Hottub
Operator's source files to reside.  There is a subdirectory in there (ui) for
the Hottub UI and operator (for the operator).

I need all new AWS resources for the new version of the application.  I don't
want to interfere with the current application.  This will allow me to develop
the new application while users continue to use the existing application.

I need a 'test' and a 'live' version of the new application.  That way in the
future I can make changes to the 'test' version of the application without
affecting the 'live' application. 

I want to replace all use of the AWS IOT service with DynamoDB.  I want to use
only DynamoDB as the backend persistence store.

I want to replace all use of AWS AppSync.  Instead, I want a REST API built on
AWS API Gateway.  Both the Hottub UI and the Hottub Controller should
communicate with the same REST API.

I want to remove all references to mysql.  At one point I tried connecting the
application to a mysql database but it never worked the way I wanted it to.
Anywhere that we need a database we should use DynamoDB.  Specifically,
hottub-mysql-dao/ mysql-lambda/ - I don't want the application to use mysql at
all.  You can ignore these and anything that uses the code inside them.

The Hottub Operator is written in ruby.  I am not fluent in Ruby and would
rather this be written in python.  The only reason it is in Ruby is that the
lib/ dir which implements the protocol that communicates with the tub is
written in Ruby.  Rewriting this whole operator and the underlying library in
python would make this easier for me to maintain.  You are on the same network
as the hottub.  You can make calls to the hottub to test out your changes.

The lambda function, currently written in nodejs should instead be written in
python. 

I want you to think about the best way of implementating this system and
suggest to me other changes that I haven't thought of.

I want you to write a Claude.md file for hottub/, hottub/ui
and hottub/operator.  The files should outline what we plan to do at a high
level.  We will continue to use those files to maintain the application going
forward.


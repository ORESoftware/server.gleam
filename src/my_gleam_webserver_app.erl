-module(my_gleam_webserver_app).
-behaviour(application).

-export([start/2, prep_stop/1, stop/1]).

start(_StartType, _StartArgs) ->
    case my_gleam_webserver:start() of
        {ok, ServerPid} ->
            logger:log(info, #{
                event => server_started,
                phase => running,
                forced => false,
                message => <<"Gleam Cowboy server started under OTP supervision">>
            }),
            {ok, ServerPid, #{server_pid => ServerPid}};
        {error, Reason} ->
            logger:log(error, #{
                event => server_start_failed,
                phase => complete,
                forced => false,
                reason => Reason
            }),
            {error, Reason}
    end.

prep_stop(State) ->
    logger:log(notice, #{
        event => shutdown_requested,
        phase => draining,
        trigger => otp_application_stop,
        forced => false,
        message => <<"OTP is stopping the application and Cowboy listener">>
    }),
    State.

stop(_State) ->
    logger:log(info, #{
        event => shutdown_complete,
        phase => complete,
        trigger => otp_application_stop,
        forced => false,
        message => <<"Gleam Cowboy application stopped">>
    }),
    ok.

-module(my_gleam_webserver_app).
-behaviour(application).

-export([start/2, stop/1]).

start(_StartType, _StartArgs) ->
    my_gleam_webserver:start(),
    {ok, self()}.

stop(_State) ->
    ok.
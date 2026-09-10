import gleam/bytes_tree.{type BytesTree}
import gleam/dict
import gleam/erlang/process
import gleam/http/cowboy
import gleam/http/request.{type Request}
import gleam/http/response.{type Response}
import ores_middleware

fn add_middleware_header(
  response_value: Response(BytesTree),
  headers,
  name: String,
) -> Response(BytesTree) {
  case dict.get(headers, name) {
    Ok(value) -> response.prepend_header(response_value, name, value)
    Error(_) -> response_value
  }
}

pub fn hello_world(_request: Request(t)) -> Response(BytesTree) {
  let config = ores_middleware.default_config("my-gleam-webserver")
  let config = ores_middleware.Config(
    ..config,
    require_https: False,
    rate_limit_enabled: False,
  )
  let assert Ok(middleware) =
    ores_middleware.create_middleware(config, ores_middleware.default_hooks())
  let middleware_request = ores_middleware.Request(
    method: "GET",
    path: "/",
    scheme: "http",
    headers: dict.new(),
    body_size: 0,
    remote_ip: "",
  )
  let middleware_response = middleware(middleware_request, fn(_) {
    ores_middleware.Response(
      status: 200,
      headers: dict.from_list([
        #("content-type", "text/plain; charset=utf-8"),
      ]),
      body: "Hello, Gleam!\n",
    )
  })
  let ores_middleware.Response(status, headers, body) = middleware_response

  response.new(status)
  |> response.set_body(bytes_tree.from_string(body))
  |> add_middleware_header(headers, "content-type")
  |> add_middleware_header(headers, "x-request-id")
  |> add_middleware_header(headers, "x-content-type-options")
  |> add_middleware_header(headers, "x-frame-options")
  |> add_middleware_header(headers, "referrer-policy")
}

pub fn start() {
  cowboy.start(hello_world, on_port: 8080)
}

pub fn main() {
  let assert Ok(_) = start()
  process.sleep_forever()
}

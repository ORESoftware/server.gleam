import gleam/bit_builder.{BitBuilder}
import gleam/http.{Request, Response}
import gleam/http/cowboy

pub fn hello_world(_request: Request(BitString)) -> Response(BitBuilder) {
  let body = bit_builder.from_string("Hello, Gleam!\n")

  http.response(200)
  |> http.prepend_resp_header("content-type", "text/plain; charset=utf-8")
  |> http.set_resp_body(body)
}

pub fn start() {
  cowboy.start(hello_world, on_port: 8080)
}

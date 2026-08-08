import gleam/bytes_tree.{type BytesTree}
import gleam/erlang/process
import gleam/http/cowboy
import gleam/http/request.{type Request}
import gleam/http/response.{type Response}

pub fn hello_world(_request: Request(t)) -> Response(BytesTree) {
  let body = bytes_tree.from_string("Hello, Gleam!\n")

  response.new(200)
  |> response.prepend_header("content-type", "text/plain; charset=utf-8")
  |> response.set_body(body)
}

pub fn start() {
  cowboy.start(hello_world, on_port: 8080)
}

pub fn main() {
  let assert Ok(_) = start()
  process.sleep_forever()
}

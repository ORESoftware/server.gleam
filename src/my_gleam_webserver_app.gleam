import gleam/http
import gleam/http/cowboy

pub fn hello_world(_request: http.Request(_)) -> http.Response {
  http.response(200)
  |> http.prepend_header("content-type", "text/plain")
  |> http.set_body("Hello, Gleam!")
}

pub external fn hello_world() -> String {
   "Hello, world from Gleam!".to_string()
}

pub fn start() {
  cowboy.start(
    8080,
    [http.cowboy_handler(hello_world)]
  )
}
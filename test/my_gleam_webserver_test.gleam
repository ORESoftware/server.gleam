import gleeunit
import gleeunit/should
import ores_middleware

pub fn main() {
  gleeunit.main()
}

pub fn middleware_contract_test() {
  ores_middleware.contract_version
  |> should.equal("1.0.0")
}

import http from "k6/http";
import { check, sleep } from "k6";
import {options} from "./basic_plan.js";

// Test configuration
exports.options = options

const PASSWORD = ''; // Reset the password on production

// Simulated user behavior
export default function () {
  let res = http.get("https://djangonaut.space/accounts/login/");
  check(res, { "status was 200": (r) => r.status == 200 });
  res = res.submitForm({
    formSelector: 'form',
    fields: { username: `load_test${__ITER}`, password: PASSWORD },
  });
  check(res, { "status was 200": (r) => r.status == 200 });
  res = http.get("https://djangonaut.space/survey_response/create/load-test/");
  check(res, { "status was 200": (r) => r.status == 200 });
  res = res.submitForm({
    formSelector: 'form',
    fields: { field_survey_1: 'load_test', field_survey_2: 2, field_survey_3: "final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. final value over 100 characters. " },
  });
  check(res, { "status was 200": (r) => r.status == 200 });
  sleep(1);
}

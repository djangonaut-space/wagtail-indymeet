import http from "k6/http";
import { check, sleep } from "k6";
import exec from 'k6/execution';

// Test configuration
export const options = {
  thresholds: {
    // Assert that 99% of requests finish within 3000ms.
    http_req_duration: ["p(99) < 3000"],
  },
  // Ramp the number of virtual users up and down
  stages: [
    { duration: "1m", target: 20 },
  ],
};

const PASSWORD = 'h@nter2!!'; // Reset the password on production

const AVAILABILITY = {
  0: [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
  1: [24.0, 24.5, 25.0, 25.5, 26.0, 26.5, 27.0, 27.5, 28.0, 28.5, 29.0],
  2: [48.0, 48.5, 49.0, 49.5, 50.0, 50.5, 51.0, 51.5, 52.0, 52.5, 53.0],
  3: [72.0, 72.5, 73.0, 73.5, 74.0, 74.5, 75.0, 75.5, 76.0, 76.5, 77.0],
}

function login(testIndex) {
  let res = http.get("https://staging.djangonaut.space/accounts/login/");
  check(res, { "status was 200": (r) => r.status == 200 });
  res = res.submitForm({
    formSelector: 'form',
    fields: {
      username: `load_test${testIndex}`,
      password: PASSWORD,
    },
    params: {
      headers: {
        'Referer': res.url,
      },
    },
  });
  check(res, { "status was 200": (r) => r.status == 200 });
}

function createAccount(testIndex) {
  let res = http.get("https://staging.djangonaut.space/accounts/signup/");
  check(res, { "status was 200": (r) => r.status == 200 });
  res = res.submitForm({
    formSelector: 'form',
    fields: {
      username: `load_test${testIndex}`,
      email: `load_test${testIndex}@test.com`,
      password1: PASSWORD,
      password2: PASSWORD,
      first_name: `first_name_${testIndex}`,
      last_name: `last_name_${testIndex}`,
      email_consent: true,
      accepted_coc: true,
    },
    params: {
      headers: {
        'Referer': res.url,
      },
    },
  });
  check(res, { "status was 200": (r) => r.status == 200 });
}

function submitApplication(testIndex) {
  let res = http.get("https://staging.djangonaut.space/survey/load-test/response/create/");
  check(res, { "status was 200": (r) => r.status == 200 });
  res = res.submitForm({
    formSelector: `form[action!='/accounts/logout/']`,
    fields: {
      field_survey_1: 'load_test',
      field_survey_2: 2,
      field_survey_3: "Final answer",
      github_username: `test-djangonautspace-${testIndex}`
    },
    params: {
      headers: {
        'Referer': res.url,
      },
    },
  });
  check(res, { "status was 200": (r) => r.status == 200 });
}

function setAvailability(testIndex) {
  let res = http.get("https://staging.djangonaut.space/accounts/availability/");
  check(res, { "status was 200": (r) => r.status == 200 });
  res = res.submitForm({
    formSelector: `form[action!='/accounts/logout/']`,
    fields: {
      slots: JSON.stringify(AVAILABILITY[testIndex % 4]),
    },
    params: {
      headers: {
        'Referer': res.url,
      },
    },
  });
  check(res, { "status was 200": (r) => r.status == 200 });
}

// Simulated user behavior
export default function () {
  createAccount(exec.scenario.iterationInTest);
  login(exec.scenario.iterationInTest)
  submitApplication(exec.scenario.iterationInTest)
  setAvailability(exec.scenario.iterationInTest)
  sleep(1);
}

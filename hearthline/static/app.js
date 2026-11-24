/** Form, place lookup, and the two API calls. Drawing a plan lives in render.js. */

import { clear, el } from "./dom.js";
import { renderPlan } from "./render.js";

var PRESETS = {
  delhi: { city: "Delhi, India", latitude: 28.6139, longitude: 77.209 },
  lahore: { city: "Lahore, Pakistan", latitude: 31.5204, longitude: 74.3587 },
  beijing: { city: "Beijing, China", latitude: 39.9042, longitude: 116.4074 },
  milan: { city: "Milan, Italy", latitude: 45.4642, longitude: 9.19 }
};

var SAMPLE_FORM = {
  city: "Delhi, India",
  adults: 2,
  children: 2,
  older_adults: 1,
  sensitive: true,
  heating: "none",
  cooking: "gas",
  purifier: false,
  commute: "car",
  distance: "2_to_8",
  transit_available: true,
  outdoor_exercise: true,
  school_run: true,
  burns_waste: true,
  audience: "household"
};

var picked = null;
var lastPayload = null;
var lookupTimer = 0;

var form = document.getElementById("day");
var errors = document.getElementById("form-errors");
var status = document.getElementById("status");
var results = document.getElementById("results");
var places = document.getElementById("places");
var city = document.getElementById("city");
var buildButton = document.getElementById("build");

function say(text) {
  status.textContent = text || "";
}

function showErrors(fields) {
  clear(errors);
  var names = Object.keys(fields || {});
  if (!names.length) return;
  errors.appendChild(el("p", { text: "Check the highlighted fields." }));
  var list = el("ul");
  names.forEach(function (name) {
    list.appendChild(el("li", { text: fields[name] }));
    var input = document.getElementById(name);
    if (input) input.setAttribute("aria-invalid", "true");
  });
  errors.appendChild(list);
}

function clearInvalid() {
  form.querySelectorAll("[aria-invalid]").forEach(function (input) {
    input.removeAttribute("aria-invalid");
  });
  clear(errors);
}

function bool(id) {
  return document.getElementById(id).checked;
}

function payload() {
  var body = {
    city: city.value.trim(),
    adults: Number(document.getElementById("adults").value),
    children: Number(document.getElementById("children").value),
    older_adults: Number(document.getElementById("older_adults").value),
    sensitive: bool("sensitive"),
    heating: document.getElementById("heating").value,
    cooking: document.getElementById("cooking").value,
    purifier: bool("purifier"),
    commute: document.getElementById("commute").value,
    distance: document.getElementById("distance").value,
    transit_available: bool("transit_available"),
    outdoor_exercise: bool("outdoor_exercise"),
    school_run: bool("school_run"),
    burns_waste: bool("burns_waste"),
    audience: document.getElementById("audience").value
  };
  if (picked) {
    body.latitude = picked.latitude;
    body.longitude = picked.longitude;
    body.city = picked.label || body.city;
  }
  return body;
}

function fill(values) {
  Object.keys(values).forEach(function (key) {
    var input = document.getElementById(key);
    if (!input) return;
    if (input.type === "checkbox") input.checked = Boolean(values[key]);
    else input.value = values[key];
  });
}

function showPlaces(list) {
  clear(places);
  (list || []).forEach(function (place) {
    var button = el("button", { type: "button", text: place.label, class: "ghost" });
    button.addEventListener("click", function () {
      picked = place;
      city.value = place.label;
      clear(places);
      say("Using " + place.label + ".");
    });
    places.appendChild(button);
  });
}

function post(url, body) {
  return fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Accept": "application/json" },
    body: JSON.stringify(body)
  }).then(function (response) {
    return response.json().then(function (data) {
      return { ok: response.ok, status: response.status, data: data };
    });
  });
}

function showPlan(plan) {
  renderPlan(results, plan, say, onAsk);
}

function onPlan(event) {
  event.preventDefault();
  clearInvalid();
  var body = payload();
  if (body.city.length < 2) {
    showErrors({ city: "Enter a city." });
    return;
  }
  buildButton.disabled = true;
  say("Checking the air, then writing the plan.");
  post("/api/plan", body).then(function (result) {
    buildButton.disabled = false;
    if (result.status === 409 && result.data.places) {
      showPlaces(result.data.places);
      say("Choose the matching place.");
      return;
    }
    if (!result.ok) {
      showErrors(result.data.fields || { form: result.data.error || "The plan could not be built." });
      say(result.data.error || "The plan could not be built.");
      return;
    }
    lastPayload = body;
    if (result.data.place) {
      picked = {
        label: result.data.place.label,
        latitude: result.data.place.latitude,
        longitude: result.data.place.longitude
      };
      city.value = result.data.place.label;
    }
    showPlan(result.data);
  }).catch(function () {
    buildButton.disabled = false;
    say("The server did not respond.");
  });
}

function onAsk(event) {
  event.preventDefault();
  if (!lastPayload) {
    say("Build a plan first.");
    return;
  }
  var question = document.getElementById("question").value.trim();
  var answer = document.getElementById("answer");
  clear(answer);
  if (!question) {
    answer.appendChild(el("p", { text: "Enter a question." }));
    return;
  }
  var body = Object.assign({}, lastPayload, { question: question });
  say("Looking at the plan.");
  post("/api/ask", body).then(function (result) {
    clear(answer);
    if (!result.ok) {
      answer.appendChild(el("p", { text: result.data.error || "The question could not be answered." }));
      return;
    }
    answer.appendChild(el("p", { text: result.data.answer }));
    if (result.data.tone) answer.appendChild(el("p", { class: "note", text: result.data.tone }));
    say("Answer ready.");
  }).catch(function () {
    clear(answer);
    answer.appendChild(el("p", { text: "The server did not respond." }));
  });
}

city.addEventListener("input", function () {
  picked = null;
  window.clearTimeout(lookupTimer);
  var value = city.value.trim();
  if (value.length < 2) {
    clear(places);
    return;
  }
  lookupTimer = window.setTimeout(function () {
    fetch("/api/places?q=" + encodeURIComponent(value), { headers: { Accept: "application/json" } })
      .then(function (response) { return response.json(); })
      .then(function (data) { showPlaces(data.places || []); })
      .catch(function () { clear(places); });
  }, 350);
});

document.querySelectorAll("[data-preset]").forEach(function (button) {
  button.addEventListener("click", function () {
    var preset = PRESETS[button.getAttribute("data-preset")];
    picked = { label: preset.city, latitude: preset.latitude, longitude: preset.longitude };
    city.value = preset.city;
    clear(places);
    form.requestSubmit();
  });
});

document.getElementById("sample").addEventListener("click", function () {
  say("Loading the sample winter day.");
  fetch("/api/sample", { headers: { Accept: "application/json" } })
    .then(function (response) { return response.json(); })
    .then(function (plan) {
      fill(SAMPLE_FORM);
      picked = { label: "Delhi, India", latitude: 28.6139, longitude: 77.209 };
      lastPayload = payload();
      showPlan(plan);
    })
    .catch(function () { say("The sample could not be loaded."); });
});

form.addEventListener("submit", onPlan);

if (new URLSearchParams(window.location.search).get("sample") === "1") {
  document.getElementById("sample").click();
}

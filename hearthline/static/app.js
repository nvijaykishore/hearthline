(function () {
  "use strict";

  var PRESETS = {
    delhi: { city: "Delhi, India", latitude: 28.6139, longitude: 77.209 },
    lahore: { city: "Lahore, Pakistan", latitude: 31.5204, longitude: 74.3587 },
    beijing: { city: "Beijing, China", latitude: 39.9042, longitude: 116.4074 },
    milan: { city: "Milan, Italy", latitude: 45.4642, longitude: 9.19 }
  };

  var BANDS = [
    "Good",
    "Moderate",
    "Unhealthy for Sensitive Groups",
    "Unhealthy",
    "Very Unhealthy",
    "Hazardous"
  ];

  var KICKER = { routine: "Routine", indoor: "Indoor", alternative: "Alternative" };
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

  function el(tag, props, children) {
    var node = document.createElement(tag);
    Object.keys(props || {}).forEach(function (key) {
      var value = props[key];
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (value === true) node.setAttribute(key, "");
      else if (value !== false && value != null) node.setAttribute(key, String(value));
    });
    (children || []).forEach(function (child) {
      if (child) node.appendChild(child);
    });
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

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

  function renderPlan(plan) {
    clear(results);
    var title = el("h2", { id: "results-title", tabindex: "-1", text: "Today in " + plan.place.label });
    results.appendChild(title);

    var air = plan.air;
    var head = el("div", { class: "air-head" }, [
      el("p", { class: "aqi-word", text: air.category }),
      el("p", { class: "aqi-num", text: "Index " + air.us_aqi + " · PM2.5 " + air.pm2_5 + " µg/m³" })
    ]);
    results.appendChild(head);
    results.appendChild(el("p", { class: "source", text: air.note + " " + air.driver }));
    if (air.guideline) results.appendChild(el("p", { class: "source", text: air.guideline }));
    if (air.clean_start) {
      results.appendChild(el("p", {
        text: "Cleaner stretch: three hours starting at " + air.clean_start + ", about " + air.clean_pm2_5 + " µg/m³ PM2.5."
      }));
    }

    var bands = el("ul", { class: "bands" });
    BANDS.forEach(function (band) {
      var item = el("li", { text: band });
      if (band === air.category) item.setAttribute("aria-current", "true");
      bands.appendChild(item);
    });
    results.appendChild(bands);

    results.appendChild(el("p", { text: plan.household_line + " " + plan.audience_line }));
    results.appendChild(el("p", { class: "callout", text: plan.summary }));
    if (plan.tone) results.appendChild(el("p", { class: "note", text: plan.tone }));
    results.appendChild(el("p", {
      class: "source",
      text: plan.narrative_source === "model"
        ? "The figures are from the calculator. A model added the short phrasing and was not allowed to add numbers."
        : "The figures and the wording both come from the calculator. Add an API key on the server when you want a model to phrase the same plan."
    }));

    var cards = el("div", { class: "cards" });
    plan.actions.forEach(function (action) {
      var steps = el("ol");
      action.steps.forEach(function (step) {
        steps.appendChild(el("li", { text: step }));
      });
      var impacts = el("ul");
      action.impacts.forEach(function (line) {
        impacts.appendChild(el("li", { class: "impact", text: line }));
      });
      var card = el("article", { class: "card" }, [
        el("p", { class: "kicker", text: KICKER[action.category] || action.category }),
        el("h3", { text: action.title }),
        steps,
        impacts
      ]);
      card.setAttribute("data-category", action.category);
      if (action.note) card.appendChild(el("p", { class: "note", text: action.note }));
      cards.appendChild(card);
    });
    results.appendChild(cards);

    var combined = plan.combined;
    var table = el("table");
    var caption = el("caption", { text: "The whole day, before and after the plan" });
    table.appendChild(caption);
    var thead = el("thead");
    var headRow = el("tr");
    ["", "Unchanged day", "This plan"].forEach(function (label) {
      headRow.appendChild(el("th", { text: label, scope: "col" }));
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    var body = el("tbody");
    [
      ["Household PM2.5 inhaled", combined.inhaled_baseline, combined.inhaled_plan],
      ["Climate pollution", combined.co2e_baseline, combined.co2e_plan],
      ["Neighborhood PM2.5 emitted", combined.emitted_baseline, combined.emitted_plan]
    ].forEach(function (row) {
      var tr = el("tr");
      tr.appendChild(el("th", { text: row[0], scope: "row" }));
      tr.appendChild(el("td", { text: row[1] }));
      tr.appendChild(el("td", { text: row[2] }));
      body.appendChild(tr);
    });
    table.appendChild(body);
    results.appendChild(table);
    results.appendChild(el("p", {
      class: "source",
      text: "Card figures are what you lose by skipping that one step after the others are in place. They are not meant to be added to this table."
    }));

    var limits = el("ul", { class: "limits" });
    plan.limits.forEach(function (line) {
      limits.appendChild(el("li", { text: line }));
    });
    results.appendChild(el("h3", { text: "Limits" }));
    results.appendChild(limits);

    var ask = el("form", { class: "ask", id: "ask" });
    ask.appendChild(el("h3", { text: "Ask about this plan" }));
    ask.appendChild(el("label", { for: "question", text: "Question" }));
    var area = el("textarea", { id: "question", name: "question", maxlength: "400" });
    area.setAttribute("aria-describedby", "ask-hint");
    ask.appendChild(area);
    ask.appendChild(el("p", { id: "ask-hint", class: "hint", text: "Exposure and routines only. Hearthline will not advise medicines." }));
    ask.appendChild(el("button", { type: "submit", text: "Ask" }));
    var answer = el("div", { id: "answer" });
    ask.appendChild(answer);
    ask.addEventListener("submit", onAsk);
    results.appendChild(ask);

    title.focus();
    say("Plan ready for " + plan.place.label + ". " + air.category + " air. " + plan.actions.length + " steps.");
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
      renderPlan(result.data);
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
        fill({
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
        });
        picked = { label: "Delhi, India", latitude: 28.6139, longitude: 77.209 };
        lastPayload = payload();
        renderPlan(plan);
      })
      .catch(function () { say("The sample could not be loaded."); });
  });

  form.addEventListener("submit", onPlan);

  if (new URLSearchParams(window.location.search).get("sample") === "1") {
    document.getElementById("sample").click();
  }
})();

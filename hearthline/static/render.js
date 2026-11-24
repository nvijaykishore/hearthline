/** Draw a finished plan. The page owns the form; this module only writes results. */

import { clear, el } from "./dom.js";

var BANDS = [
  "Good",
  "Moderate",
  "Unhealthy for Sensitive Groups",
  "Unhealthy",
  "Very Unhealthy",
  "Hazardous"
];

var KICKER = { routine: "Routine", indoor: "Indoor", alternative: "Alternative" };

var TOTAL_ROWS = [
  ["Household PM2.5 inhaled", "inhaled_baseline", "inhaled_plan"],
  ["Climate pollution", "co2e_baseline", "co2e_plan"],
  ["Neighborhood PM2.5 emitted", "emitted_baseline", "emitted_plan"]
];

function renderAir(results, plan) {
  var air = plan.air;
  results.appendChild(el("div", { class: "air-head" }, [
    el("p", { class: "aqi-word", text: air.category }),
    el("p", { class: "aqi-num", text: "Index " + air.us_aqi + " · PM2.5 " + air.pm2_5 + " µg/m³" })
  ]));
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
}

function renderCards(results, plan) {
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
}

function renderTotals(results, plan) {
  var combined = plan.combined;
  var table = el("table");
  table.appendChild(el("caption", { text: "The whole day, before and after the plan" }));
  var headRow = el("tr");
  ["", "Unchanged day", "This plan"].forEach(function (label) {
    headRow.appendChild(el("th", { text: label, scope: "col" }));
  });
  table.appendChild(el("thead", null, [headRow]));
  var body = el("tbody");
  TOTAL_ROWS.forEach(function (row) {
    var tr = el("tr");
    tr.appendChild(el("th", { text: row[0], scope: "row" }));
    tr.appendChild(el("td", { text: combined[row[1]] }));
    tr.appendChild(el("td", { text: combined[row[2]] }));
    body.appendChild(tr);
  });
  table.appendChild(body);
  results.appendChild(table);
  results.appendChild(el("p", {
    class: "source",
    text: "Card figures are what you lose by skipping that one step after the others are in place. They are not meant to be added to this table."
  }));
}

function renderLimits(results, plan) {
  var limits = el("ul", { class: "limits" });
  plan.limits.forEach(function (line) {
    limits.appendChild(el("li", { text: line }));
  });
  results.appendChild(el("h3", { text: "Limits" }));
  results.appendChild(limits);
}

function renderAsk(results, onAsk) {
  var ask = el("form", { class: "ask", id: "ask" });
  ask.appendChild(el("h3", { text: "Ask about this plan" }));
  ask.appendChild(el("label", { for: "question", text: "Question" }));
  var area = el("textarea", { id: "question", name: "question", maxlength: "400" });
  area.setAttribute("aria-describedby", "ask-hint");
  ask.appendChild(area);
  ask.appendChild(el("p", { id: "ask-hint", class: "hint", text: "Exposure and routines only. Hearthline will not advise medicines." }));
  ask.appendChild(el("button", { type: "submit", text: "Ask" }));
  ask.appendChild(el("div", { id: "answer" }));
  ask.addEventListener("submit", onAsk);
  results.appendChild(ask);
}

export function renderPlan(results, plan, say, onAsk) {
  clear(results);
  var title = el("h2", { id: "results-title", tabindex: "-1", text: "Today in " + plan.place.label });
  results.appendChild(title);
  renderAir(results, plan);
  renderCards(results, plan);
  renderTotals(results, plan);
  renderLimits(results, plan);
  renderAsk(results, onAsk);
  title.focus();
  say("Plan ready for " + plan.place.label + ". " + plan.air.category + " air. " + plan.actions.length + " steps.");
}

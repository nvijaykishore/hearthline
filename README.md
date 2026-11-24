# Hearthline

Hearthline is a day plan for a household, a school, or a block on a severe winter smog day. It turns the place and the way people actually live into three kinds of advice: a lower-emission routine, an indoor air step, and a sustainable swap. Each one is paired with the change it makes.

## Chosen vertical

Household and neighborhood action during severe winter urban smog.

The person using it is deciding what to do today: whether the child plays outside, when to open a window, what to do with the school run, and whether a bag gets burned in the lane. It is not a medical device, not a permit tool, and not a replacement for an official air-quality bulletin.

## Approach

The figures are calculated before any model speaks.

A deterministic day model compares the unchanged day with a recommended day. Card text is allowed to quote only those results. When `XAI_API_KEY` is set, Grok (`grok-4.7` on the xAI Responses API) may add a short phrasing. That request is sent with `store: false`, the key stays on the server, and any reply that contains a digit or a banned claim (a diagnosis, a cure, an ozone generator) is dropped. The figures on screen do not change. With no key, the same plan is still complete.

That split is the product. A language model is a poor place to invent a dose, and a dose with no explanation is a poor thing to hand a family.

## How a plan is made

The page collects a place and a lifestyle, and nothing clinical beyond a yes or no for “someone is more sensitive.” The server resolves the place, reads current and hourly PM2.5 from Open-Meteo, and builds two days: the one implied by the form, and a recommended day. The headline is the full recommended day against the unchanged day. Each card is what changes if that one choice is removed and the rest of the plan stays. Those two views overlap, so the cards are not meant to be added up to the headline.

Air data is cached for twenty minutes. The browser talks only to this server. Outbound requests are limited to Open-Meteo and `api.x.ai`.

The factors and the policy live in `hearthline/impact.py`. The sentences live in `hearthline/present.py`. The page is static files under `hearthline/static/` and does not inject HTML from the response.

Open `/?sample=1` to see a full illustrative winter morning without the network.

## Assumptions

These are planning estimates for one day. They are not a personal exposure measurement.

- Outdoor PM2.5 is treated as uniform at the reported value. The US AQI scale is only the label. The dose uses micrograms.
- With winter windows closed, indoor air starts at a fixed fraction of outdoor air, then cooking and heating add during their own hours. The fraction and the additions are named constants in `hearthline/impact.py`, which is the source of truth if this paragraph and the code ever disagree.
- One adult commutes. If a child lives there, outdoor play is counted for one child. A mask credit applies to an adult outdoors, not to an infant and not inside a vehicle.
- A school run adds a wait. It adds a separate short car trip only when the adult is otherwise at home.
- Wood smoke and a burned bag use a per-evening and a per-bag factor. Real piles vary, and the card says so.
- A commute that would lengthen time in the plume on a hazardous day is refused, even when it would cut climate pollution.
- Open-Meteo is a model mosaic, not a regulatory monitor. The page says that on every plan.
- The model has no knowledge of live air. The reading is fetched, not asked of the model.

## Run

```powershell
python -m unittest discover -s tests -v
python -m hearthline
```

Then open http://127.0.0.1:8000 . Copy `.env.example` to `.env` only if you want model phrasing. A `.env` in the working directory is read at startup and never overrides variables that are already set. The key is not sent to the browser.

The same app is deployed at https://hearthline-black.vercel.app .

## Walkthrough

`docs/hearthline-walkthrough.mp4` follows one Delhi sample morning: the household form, the air reading, a lower-emission routine, an indoor step, a cleaner trip, and the rule that a model may phrase the plan and cannot change the figures.

## Limits

Hearthline will not diagnose, prescribe, or help hide burning or spoof a monitor. Breathing trouble is urgent care, not a follow-up question. The cleaner-hours window is a forecast band, and a fixed commute clock cannot always move into it, so trip math stays on the current hour.

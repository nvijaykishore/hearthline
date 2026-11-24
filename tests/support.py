"""Shared household JSON for HTTP tests. Not collected by unittest."""


def household_payload(**overrides):
    body = {
        "city": "Delhi, India",
        "adults": 2,
        "children": 1,
        "older_adults": 0,
        "sensitive": True,
        "heating": "none",
        "cooking": "gas",
        "purifier": False,
        "commute": "car",
        "distance": "2_to_8",
        "transit_available": True,
        "outdoor_exercise": True,
        "school_run": True,
        "burns_waste": False,
        "audience": "household",
    }
    body.update(overrides)
    return body

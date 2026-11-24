/** Small DOM helpers. Text is assigned with textContent, never HTML. */

export function el(tag, props, children) {
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

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

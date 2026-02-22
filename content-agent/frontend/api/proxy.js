module.exports = async (req, res) => {
  const backendBase = "http://3.95.64.139";
  const rawPath = req.query.path || "";
  const path = Array.isArray(rawPath) ? rawPath.join("/") : rawPath;
  const forwardedQuery = new URLSearchParams();
  Object.entries(req.query || {}).forEach(([key, value]) => {
    if (key === "path") return;
    if (Array.isArray(value)) {
      value.forEach((v) => forwardedQuery.append(key, v));
    } else if (typeof value !== "undefined") {
      forwardedQuery.append(key, String(value));
    }
  });
  const queryString = forwardedQuery.toString();
  const target = `${backendBase}/api/${path}${queryString ? `?${queryString}` : ""}`;

  const headers = { ...req.headers };
  delete headers.host;
  delete headers.connection;
  delete headers["content-length"];

  const method = req.method || "GET";
  const init = { method, headers };

  if (!["GET", "HEAD"].includes(method)) {
    init.body = JSON.stringify(req.body ?? {});
  }

  try {
    const response = await fetch(target, init);
    const text = await response.text();

    res.statusCode = response.status;
    response.headers.forEach((value, key) => {
      if (!["content-encoding", "transfer-encoding", "connection"].includes(key.toLowerCase())) {
        res.setHeader(key, value);
      }
    });

    res.send(text);
  } catch (error) {
    res.status(502).json({ detail: `Proxy failed: ${error.message}` });
  }
};

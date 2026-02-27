module.exports = async (req, res) => {
  const backendBases = [
    process.env.BACKEND_BASE_URL,
    process.env.BACKEND_FALLBACK_URL,
    "http://ec2-52-91-158-161.compute-1.amazonaws.com",
    "http://52.91.158.161"
  ].filter(Boolean);
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

  const headers = {};
  if (req.headers.authorization) headers.Authorization = req.headers.authorization;
  if (req.headers["content-type"]) headers["Content-Type"] = req.headers["content-type"];

  const method = req.method || "GET";
  const init = { method, headers, redirect: "manual" };

  if (!["GET", "HEAD"].includes(method)) {
    if (typeof req.body === "string") {
      init.body = req.body;
    } else if (req.body && Object.keys(req.body).length > 0) {
      init.body = JSON.stringify(req.body);
    }
  }

  try {
    let response = null;
    let lastError = null;
    let target = "";

    for (const backendBase of backendBases) {
      target = `${backendBase}/api/${path}${queryString ? `?${queryString}` : ""}`;
      try {
        response = await fetch(target, init);
        break;
      } catch (error) {
        lastError = error;
      }
    }

    if (!response) {
      throw lastError || new Error("No backend targets configured");
    }

    const location = response.headers.get("location");
    if (location && [301, 302, 303, 307, 308].includes(response.status)) {
      res.statusCode = response.status;
      res.setHeader("Location", location);
      res.end();
      return;
    }

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

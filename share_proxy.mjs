import http from "node:http";
import fs from "node:fs";

const HOST = "127.0.0.1";
const PORT = 3100;

const ROOT =
  process.env.HOME + "/ClearNasdaq/clear_nasdaq_fia-2";

const LOGS = ROOT + "/runtime_logs";

function sendCached(res, file) {
  try {
    const body = fs.readFileSync(file);

    res.writeHead(200, {
      "content-type": "application/json",
      "cache-control": "no-store",
    });

    res.end(body);
  } catch {
    res.writeHead(503, {
      "content-type": "application/json",
    });

    res.end(JSON.stringify({
      ok: false,
      error: "CACHE_NOT_READY",
    }));
  }
}

function proxyTo(port, req, res) {
  const upstream = http.request({
    hostname: HOST,
    port,
    path: req.url,
    method: req.method,
    headers: {
      ...req.headers,
      host: `${HOST}:${port}`,
    },
  }, response => {
    res.writeHead(
      response.statusCode || 502,
      response.headers
    );

    response.pipe(res);
  });

  upstream.on("error", err => {
    res.writeHead(502, {
      "content-type": "application/json",
    });

    res.end(JSON.stringify({
      ok: false,
      error: "PROXY_ERROR",
      detail: err.message,
    }));
  });

  req.pipe(upstream);
}

const server = http.createServer((req, res) => {

  // Fast cached live data
  if (req.url.startsWith("/api/forecast")) {
    return sendCached(
      res,
      LOGS + "/public_forecast.json"
    );
  }

  if (req.url.startsWith("/api/liquidity")) {
    return sendCached(
      res,
      LOGS + "/public_liquidity.json"
    );
  }

  // IMPORTANT:
  // These are Next.js server routes, NOT FastAPI routes.
  if (
    req.url.startsWith("/api/fia/") ||
    req.url.startsWith("/api/phase33/") ||
    req.url.startsWith("/api/phase34/")
  ) {
    return proxyTo(3000, req, res);
  }

  // Direct FastAPI endpoints
  if (req.url.startsWith("/api/")) {
    return proxyTo(8001, req, res);
  }

  // Dashboard HTML, JS, CSS
  return proxyTo(3000, req, res);
});

server.listen(PORT, HOST, () => {
  console.log("CLEAR NASDAQ SHARE PROXY LIVE ON 3100");
});

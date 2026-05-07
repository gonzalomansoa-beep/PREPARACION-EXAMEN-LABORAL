const https = require("https");

// Scheduled function: keeps Railway awake every 5 minutes
exports.handler = async () => {
  return new Promise((resolve) => {
    const req = https.request(
      {
        hostname: "preparacion-examen-laboral-production.up.railway.app",
        port: 443,
        path: "/health",
        method: "GET",
      },
      (res) => {
        let data = "";
        res.on("data", (c) => (data += c));
        res.on("end", () => {
          console.log("Railway ping OK:", data);
          resolve({ statusCode: 200, body: "ok" });
        });
      }
    );
    req.on("error", (e) => {
      console.error("Railway ping error:", e.message);
      resolve({ statusCode: 500, body: "error" });
    });
    req.setTimeout(25000, () => {
      req.destroy();
      console.log("Railway ping timeout (cold start expected)");
      resolve({ statusCode: 408, body: "timeout" });
    });
    req.end();
  });
};

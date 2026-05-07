const https = require("https");

exports.handler = async (event) => {
  if (event.httpMethod !== "POST") {
    return { statusCode: 405, body: "Method Not Allowed" };
  }

  const body = event.body;

  return new Promise((resolve) => {
    const options = {
      hostname: "preparacion-examen-laboral-production.up.railway.app",
      port: 443,
      path: "/contacto",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
      },
    };

    const req = https.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        resolve({
          statusCode: 200,
          headers: { "Content-Type": "application/json" },
          body: data,
        });
      });
    });

    req.on("error", (e) => {
      resolve({
        statusCode: 500,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ok: false, error: e.message }),
      });
    });

    req.setTimeout(25000, () => {
      req.destroy();
      resolve({
        statusCode: 504,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ok: false,
          error: "El servidor tardó demasiado en responder. Inténtalo de nuevo.",
        }),
      });
    });

    req.write(body);
    req.end();
  });
};

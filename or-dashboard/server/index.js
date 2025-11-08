import express from "express";
import cors from "cors";
import dotenv from "dotenv";
import {
  getKPI,
  getTrend,
  getRoomUtil,
  getFirstCut,
  getTopOps,
  getPostpone,
  getHeatmap
} from "./queries.js";

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json());

function asyncRoute(handler) {
  return async (req, res) => {
    try {
      await handler(req, res);
    } catch (error) {
      console.error("[or-dashboard]", error);
      res.status(500).json({ error: error?.message || "Unexpected server error" });
    }
  };
}

app.get("/api/health", (req, res) => {
  res.json({ ok: true, timestamp: new Date().toISOString() });
});

app.get(
  "/api/kpi",
  asyncRoute(async (req, res) => {
    const data = await getKPI(req.query);
    res.json(data);
  })
);

app.get(
  "/api/trend",
  asyncRoute(async (req, res) => {
    const data = await getTrend(req.query);
    res.json(data);
  })
);

app.get(
  "/api/rooms/utilization",
  asyncRoute(async (req, res) => {
    const data = await getRoomUtil(req.query);
    res.json(data);
  })
);

app.get(
  "/api/surgeons/firstcut",
  asyncRoute(async (req, res) => {
    const data = await getFirstCut(req.query);
    res.json(data);
  })
);

app.get(
  "/api/top-operations",
  asyncRoute(async (req, res) => {
    const data = await getTopOps(req.query);
    res.json(data);
  })
);

app.get(
  "/api/postponements",
  asyncRoute(async (req, res) => {
    const data = await getPostpone(req.query);
    res.json(data);
  })
);

app.get(
  "/api/heatmap",
  asyncRoute(async (req, res) => {
    const data = await getHeatmap(req.query);
    res.json(data);
  })
);

const port = Number(process.env.PORT || 4000);
app.listen(port, () => {
  console.log(`OR Dashboard API listening on :${port}`);
});

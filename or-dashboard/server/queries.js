import dotenv from "dotenv";
import { pool } from "./db.js";

dotenv.config();

const DURATION_MINUTES = "TIMESTAMPDIFF(MINUTE, time_start, time_end)";

function parseBoolean(value) {
  if (value === undefined || value === null) {
    return undefined;
  }
  const normalized = String(value).trim().toLowerCase();
  if (!normalized) {
    return undefined;
  }
  if (["1", "true", "yes", "y"].includes(normalized)) {
    return true;
  }
  if (["0", "false", "no", "n"].includes(normalized)) {
    return false;
  }
  return undefined;
}

function buildFilters(query = {}) {
  const conditions = [];
  const params = [];

  const map = {
    from: "date >= ?",
    to: "date <= ?",
    room_id: "room_id = ?",
    doctor: "doctor = ?",
    department: "department = ?",
    operation: "operation = ?",
    case_size: "case_size = ?"
  };

  Object.entries(map).forEach(([key, clause]) => {
    const raw = query[key];
    if (raw === undefined || raw === null) {
      return;
    }
    const value = String(raw).trim();
    if (!value) {
      return;
    }
    conditions.push(clause);
    params.push(value);
  });

  const postponed = parseBoolean(query.is_postponed);
  if (postponed !== undefined) {
    conditions.push("is_postponed = ?");
    params.push(postponed ? 1 : 0);
  }

  const cancelled = parseBoolean(query.is_cancelled);
  if (cancelled !== undefined) {
    conditions.push("is_cancelled = ?");
    params.push(cancelled ? 1 : 0);
  }

  return { conditions, params };
}

function buildWhere(conditions) {
  if (!conditions.length) {
    return "";
  }
  return `WHERE ${conditions.join(" AND ")}`;
}

function availableMinutesPerRoomDay() {
  const [startHour, startMinute] = (process.env.BLOCK_START || "08:00").split(":").map(Number);
  const [endHour, endMinute] = (process.env.BLOCK_END || "16:00").split(":").map(Number);
  const startTotal = startHour * 60 + startMinute;
  const endTotal = endHour * 60 + endMinute;
  const diff = Math.max(endTotal - startTotal, 0);
  return diff || 480; // default 8 hours
}

function secondsToHHMM(seconds) {
  const safe = Math.max(Number(seconds) || 0, 0);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`;
}

export async function getKPI(query) {
  const { conditions, params } = buildFilters(query);
  conditions.push("time_start IS NOT NULL");
  conditions.push("time_end IS NOT NULL");
  const whereClause = buildWhere(conditions);

  const sql = `
    SELECT
      COUNT(*) AS cases,
      SUM(${DURATION_MINUTES}) AS case_minutes,
      COUNT(DISTINCT CONCAT(room_id, '#', date)) AS room_days,
      SUM(CASE WHEN is_postponed = 1 THEN 1 ELSE 0 END) AS postponed_cases,
      SUM(CASE WHEN is_cancelled = 1 THEN 1 ELSE 0 END) AS cancelled_cases
    FROM or_cases
    ${whereClause}
  `;

  const [rows] = await pool.query(sql, params);
  const result = rows[0] || {};
  const roomDays = Number(result.room_days) || 0;
  const caseMinutes = Number(result.case_minutes) || 0;
  const caseCount = Number(result.cases) || 0;
  const availMinutes = roomDays * availableMinutesPerRoomDay();

  return {
    cases: caseCount,
    case_min: caseMinutes,
    avail_min: availMinutes,
    utilization_pct: availMinutes ? Number(((caseMinutes / availMinutes) * 100).toFixed(1)) : 0,
    postponed_cases: Number(result.postponed_cases) || 0,
    cancelled_cases: Number(result.cancelled_cases) || 0,
    avg_case_min: caseCount ? Number((caseMinutes / caseCount).toFixed(1)) : 0
  };
}

export async function getTrend(query) {
  const granularity = ["day", "month", "year"].includes(query?.granularity)
    ? query.granularity
    : "day";

  let bucketExpression;
  switch (granularity) {
    case "month":
      bucketExpression = "DATE_FORMAT(date, '%Y-%m')";
      break;
    case "year":
      bucketExpression = "DATE_FORMAT(date, '%Y')";
      break;
    default:
      bucketExpression = "DATE_FORMAT(date, '%Y-%m-%d')";
  }

  const { conditions, params } = buildFilters(query);
  conditions.push("time_start IS NOT NULL");
  conditions.push("time_end IS NOT NULL");
  const whereClause = buildWhere(conditions);

  const sql = `
    WITH bucketed AS (
      SELECT
        ${bucketExpression} AS bucket,
        room_id,
        ${DURATION_MINUTES} AS duration_minutes
      FROM or_cases
      ${whereClause}
    )
    SELECT
      bucket,
      COUNT(*) AS cases,
      SUM(duration_minutes) AS case_minutes,
      COUNT(DISTINCT CONCAT(room_id, '#', bucket)) AS room_buckets
    FROM bucketed
    GROUP BY bucket
    ORDER BY bucket
  `;

  const [rows] = await pool.query(sql, params);
  const minutesPerRoomDay = availableMinutesPerRoomDay();

  return rows.map((row) => {
    const caseMinutes = Number(row.case_minutes) || 0;
    const roomBuckets = Number(row.room_buckets) || 0;
    const available = roomBuckets * minutesPerRoomDay;
    return {
      bucket: row.bucket,
      cases: Number(row.cases) || 0,
      case_min: caseMinutes,
      utilization_pct: available ? Number(((caseMinutes / available) * 100).toFixed(1)) : 0
    };
  });
}

export async function getRoomUtil(query) {
  const { conditions, params } = buildFilters(query);
  conditions.push("time_start IS NOT NULL");
  conditions.push("time_end IS NOT NULL");
  const whereClause = buildWhere(conditions);

  const sql = `
    SELECT
      room_id,
      COUNT(*) AS cases,
      SUM(${DURATION_MINUTES}) AS case_minutes,
      COUNT(DISTINCT CONCAT(room_id, '#', date)) AS room_days
    FROM or_cases
    ${whereClause}
    GROUP BY room_id
    ORDER BY case_minutes DESC
  `;

  const [rows] = await pool.query(sql, params);
  const minutesPerRoomDay = availableMinutesPerRoomDay();

  return rows.map((row) => {
    const roomDays = Number(row.room_days) || 0;
    const caseMinutes = Number(row.case_minutes) || 0;
    const cases = Number(row.cases) || 0;
    const available = roomDays * minutesPerRoomDay;
    return {
      room_id: row.room_id,
      cases,
      avg_case_min: cases ? Number((caseMinutes / cases).toFixed(1)) : 0,
      utilization_pct: available ? Number(((caseMinutes / available) * 100).toFixed(1)) : 0,
      idle_min: available ? Math.max(available - caseMinutes, 0) : null
    };
  });
}

export async function getFirstCut(query) {
  const { conditions, params } = buildFilters(query);
  conditions.push("time_start IS NOT NULL");
  const whereClause = buildWhere(conditions);

  const sql = `
    WITH first_cut AS (
      SELECT
        doctor,
        date,
        MIN(TIME(time_start)) AS first_time
      FROM or_cases
      ${whereClause}
      GROUP BY doctor, date
    )
    SELECT
      doctor,
      AVG(TIME_TO_SEC(first_time)) AS avg_first_seconds,
      COUNT(*) AS workdays
    FROM first_cut
    GROUP BY doctor
    HAVING workdays >= 3
    ORDER BY avg_first_seconds ASC
  `;

  const [rows] = await pool.query(sql, params);

  return rows.map((row) => {
    const seconds = Number(row.avg_first_seconds) || 0;
    return {
      doctor: row.doctor,
      avg_first_minutes: Number((seconds / 60).toFixed(1)),
      avg_first_time: secondsToHHMM(seconds),
      workdays: Number(row.workdays) || 0
    };
  });
}

export async function getTopOps(query) {
  const { conditions, params } = buildFilters(query);
  conditions.push("time_start IS NOT NULL");
  conditions.push("time_end IS NOT NULL");
  const whereClause = buildWhere(conditions);

  const sql = `
    SELECT
      operation,
      COUNT(*) AS cases,
      AVG(${DURATION_MINUTES}) AS avg_minutes,
      SUM(${DURATION_MINUTES}) AS total_minutes
    FROM or_cases
    ${whereClause}
    GROUP BY operation
    ORDER BY cases DESC
    LIMIT 15
  `;

  const [rows] = await pool.query(sql, params);
  return rows.map((row) => ({
    operation: row.operation,
    cases: Number(row.cases) || 0,
    avg_min: row.avg_minutes ? Number(Number(row.avg_minutes).toFixed(1)) : 0,
    total_min: Number(row.total_minutes) || 0
  }));
}

export async function getPostpone(query) {
  const { conditions, params } = buildFilters(query);
  conditions.push("is_postponed = 1");
  const whereClause = buildWhere(conditions);

  const sql = `
    SELECT
      postponed_reason AS reason,
      COUNT(*) AS cases
    FROM or_cases
    ${whereClause}
    GROUP BY postponed_reason
    ORDER BY cases DESC
  `;

  const [rows] = await pool.query(sql, params);
  return rows.map((row) => ({
    reason: row.reason || "Unknown",
    cases: Number(row.cases) || 0
  }));
}

export async function getHeatmap(query) {
  const { conditions, params } = buildFilters(query);
  conditions.push("time_start IS NOT NULL");
  conditions.push("time_end IS NOT NULL");
  const whereClause = buildWhere(conditions);

  const sql = `
    SELECT
      DAYOFWEEK(date) AS dow,
      HOUR(time_start) AS hour,
      COUNT(*) AS cases,
      SUM(${DURATION_MINUTES}) AS case_minutes
    FROM or_cases
    ${whereClause}
    GROUP BY DAYOFWEEK(date), HOUR(time_start)
    ORDER BY dow, hour
  `;

  const [rows] = await pool.query(sql, params);
  return rows.map((row) => ({
    dow: Number(row.dow) || 0,
    hour: Number(row.hour) || 0,
    cases: Number(row.cases) || 0,
    case_min: Number(row.case_minutes) || 0
  }));
}

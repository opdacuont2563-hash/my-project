# OR Dashboard Starter Kit

This starter kit pairs a REST API (Node.js + Express + MySQL) with a Vite + React single-page dashboard for monitoring operating-room performance metrics.

## Structure

```
or-dashboard/
├── server/          # Express API with MySQL queries
└── client/          # React dashboard (Vite)
```

## Quick start

1. **Install dependencies**
   ```bash
   cd server
   npm install
   cp .env.example .env   # update database credentials
   npm run dev            # start API on http://localhost:4000
   ```

2. **Start the dashboard**
   ```bash
   cd ../client
   npm install
   cp .env.example .env   # optional – defaults to http://localhost:4000
   npm run dev            # opens Vite dev server on http://localhost:5173
   ```

The dashboard consumes the REST endpoints exposed by the server. Adjust SQL in `server/queries.js` to match your schema.

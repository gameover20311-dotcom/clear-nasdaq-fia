# CLEAR NASDAQ FIA — Professional Dashboard v1

This package upgrades the existing Next.js frontend only.

Files:
- app/page.tsx
- app/globals.css

It keeps the existing backend contract at:
http://localhost:8000/api/forecast

It does NOT fabricate performance/backtest metrics. The Performance Engine section is a placeholder until historical evaluation data is connected.

Install:
1. Back up your current frontend:
   cp app/page.tsx app/page.tsx.backup
   cp app/globals.css app/globals.css.backup

2. Replace the two files with the supplied files.

3. Keep the backend running on port 8000.

4. Keep the Next.js frontend running:
   npm run dev

5. Open:
   http://localhost:3000

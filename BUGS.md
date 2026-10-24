# Bugs found and fixed

All line numbers point to the **original** code (commit `c36b150`).
The list covers 11 bugs in the app itself, plus a 12th bug in the setup code that I hit
while connecting to MySQL.

How I worked:
1. Read the whole backend and frontend and compared what each API **sends** with what the
   React code **expects**.
2. Ran the app and checked the UI, the browser Network tab and the Flask log.
3. Wrote a smoke test that calls every API endpoint, first on SQLite and then on the real
   MySQL database. All checks pass.

---

## Backend

### 1. Pagination skips the first page
- **How I found it:** The table showed the 11th to 20th newest expenses, not the newest 10.
  The new expense I had just added was missing from page 1. Code reading showed why.
- **Root cause:** `backend/app.py` line 55: `offset = page * per_page`. Pages start at 1,
  so page 1 skips 10 rows.
- **Fix:** `offset = (page - 1) * per_page`. Also made sure `page` and `per_page` are at
  least 1.
- **Verified:** With 15 expenses, page 1 returns 10 and page 2 returns 5, and no expense
  appears on both pages.

### 2. Deleted expenses still show in the list
- **How I found it:** After I clicked "Delete", the row stayed in the table and the total
  did not change. The Network tab showed `DELETE` returning `{"ok": true}`.
- **Root cause:** `backend/app.py` lines 56 and 58. Delete is a "soft delete" (it sets
  `is_deleted = 1`), but `list_expenses` never filters on `is_deleted`. The `total` count
  includes deleted rows too.
- **Fix:** Filter with `Expense.is_deleted == 0` and count from the same filtered query.
  Deleting an expense that is already deleted now returns 404.
- **Verified:** Total goes from 15 to 14 after a delete, and deleting it again gives 404.

### 3. Monthly trend chart always shows an error
- **How I found it:** The "Monthly trend" card showed the error
  `Cannot read properties of undefined (reading 'map')`. In the Network tab, the response
  had keys `trend_rows`, `period` and `spend`.
- **Root cause:** `backend/app.py` lines 171-172 send
  `{"trend_rows": [{"period", "spend"}]}`, but `frontend/src/App.jsx` line 62 reads
  `data.monthly_series` with `month` and `total`. The names don't match.
- **Fix:** The backend now sends `{"monthly_series": [{"month", "total"}]}`. The frontend
  also checks `r.ok` and falls back to an empty list.
- **Verified:** The endpoint returns 6 months, and the chart shows 6 bars.

### 4. Amount is stored as text and never checked
- **How I found it:** I could save an amount like `abc` or `-5`. After that, the reporting
  charts stopped loading: the Flask log showed
  `ValueError: could not convert string to float` and the API returned 500.
- **Root cause:** `backend/models.py` line 18 and `backend/schema.sql` line 13 store
  `amount` as `VARCHAR(32)`. `backend/app.py` line 91 saves whatever was sent.
  Lines 87 and 93 also crash with a 500 on a bad `category_id` or date.
- **Fix:** Changed the column to `DECIMAL(10,2)` (model + schema). The API now checks that
  the amount is a number greater than 0 and rounds it to 2 decimals. A bad category or a
  date not in `YYYY-MM-DD` format returns 400 with a clear message instead of 500.
- **Verified:** `abc`, `-5`, `NaN`, category `x`, category `999999` and date `24-10-2026`
  all return 400. Good amounts come back as `"10.50"`.

### 5. Deleting a category that has expenses crashes
- **How I found it:** Code reading, then I called `DELETE /api/categories/<id>` on a
  category that had expenses. MySQL returned a foreign key error and the API returned 500.
- **Root cause:** `backend/app.py` line 47 hard-deletes the category. Expenses still point
  to it through a foreign key, even soft-deleted ones, so MySQL refuses.
- **Fix:** If the category still has expenses, return `409 "category has expenses"`. An
  unused category is deleted normally.
- **Verified:** Category in use gives 409. Empty category gives 200.

### 6. Monthly report crashes on a bad month and uses UTC for "today"
- **How I found it:** I typed month `13` in the Reporting card. The Network tab showed a
  500, and the Flask log showed `ValueError: month must be in 1..12`.
- **Root cause:** `backend/app.py` lines 123-127 pass year and month straight into `date()`
  with no check. "Today" uses `datetime.utcnow()`, which can be a different day (or month)
  than the user's local date. Line 157 has the same UTC problem in the trend report.
- **Fix:** Return 400 if the month is not 1-12. Use `date.today()` (local date) in both
  reports.
- **Verified:** `?month=13` returns 400, and the default month is the current local month.

---

## Frontend

### 7. Category bar chart is empty
- **How I found it:** The Reporting chart showed axes but no bars. The Network tab showed
  correct data, e.g. `{"name": "Food", "amt": 4720.25}`.
- **Root cause:** `frontend/src/App.jsx` line 256: `<Bar dataKey="value">`. The data has no
  `value` field; the amount is in `amt`.
- **Fix:** `<Bar dataKey="amt">`.
- **Verified:** The chart shows one bar per category (Rent, Food, Travel, Shopping).

### 8. "Sum on this page" joins strings instead of adding numbers
- **How I found it:** With amounts 12.50 and 5, the UI showed `012.505` instead of `17.50`.
  The label even said "(strings)".
- **Root cause:** `frontend/src/App.jsx` line 136: `a + e.amount`. The API sends amount as
  a string, so `+` joins the text together.
- **Fix:** `a + (parseFloat(e.amount) || 0)`, shown with `.toFixed(2)`. I also removed
  "(strings)" from the label.
- **Verified:** The sum shows a correct number with 2 decimals.

### 9. The last page can't be reached
- **How I found it:** With 15 expenses the pager said "Page 1 / 1 (total 15)" and "Next" was
  disabled. Expenses 11-15 could never be seen.
- **Root cause:** `frontend/src/App.jsx` line 137: `Math.floor(total / perPage)` rounds
  15/10 down to 1.
- **Fix:** `Math.ceil(total / perPage)` rounds up, so 15/10 = 2 pages.
- **Verified:** The pager shows "Page 1 / 2" and "Next" opens the last 5 expenses.

### 10. The default date can be yesterday
- **How I found it:** Code reading. In India (UTC+5:30), an expense added before 5:30 am
  without picking a date gets yesterday's date.
- **Root cause:** `frontend/src/App.jsx` line 107: `new Date().toISOString().slice(0, 10)`.
  `toISOString()` always gives the UTC date.
- **Fix:** Added a small `localToday()` helper that builds `YYYY-MM-DD` from the local
  year, month and day.
- **Verified:** The default date matches the local calendar date.

### 11. Deleting the last row on the last page leaves an empty page
- **How I found it:** With 11 expenses I went to page 2 (1 row) and deleted it. The table
  went empty and showed "Page 2 / 1".
- **Root cause:** `frontend/src/App.jsx` around line 330: `page` is never adjusted when
  `totalPages` gets smaller.
- **Fix:** A `useEffect` moves back to the last page whenever `page > totalPages`.
- **Verified:** After the delete, the app goes back to page 1 and shows the remaining rows.

---

## Bonus: setup bug

### 12. Backend can't connect when the MySQL password has special characters
- **How I found it:** The Flask log on startup showed
  `Can't connect to MySQL server on '...@127.0.0.1' (getaddrinfo failed)`. Part of the
  password was being read as the host name.
- **Root cause:** `backend/config.py` line 11 puts the password straight into the database
  URL. A character like `@` in the password splits the URL in the wrong place.
- **Fix:** URL-encode the user and password with `urllib.parse.quote_plus`.
- **Verified:** The backend starts and `GET /api/categories` returns JSON.

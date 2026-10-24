"""
Expense Tracker API — Flask + MySQL.
"""
from datetime import datetime, date
from calendar import monthrange
from decimal import Decimal, InvalidOperation

from flask import Flask, jsonify, request
from flask_cors import CORS

from config import Config
from models import db, Category, Expense


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)
    CORS(app)

    with app.app_context():
        db.create_all()

    @app.route("/api/categories", methods=["GET"])
    def list_categories():
        rows = Category.query.order_by(Category.name).all()
        return jsonify([{"id": c.id, "name": c.name} for c in rows])

    @app.route("/api/categories", methods=["POST"])
    def create_category():
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name required"}), 400
        if Category.query.filter_by(name=name).first():
            return jsonify({"error": "exists"}), 409
        c = Category(name=name)
        db.session.add(c)
        db.session.commit()
        return jsonify({"id": c.id, "name": c.name}), 201

    @app.route("/api/categories/<int:cid>", methods=["DELETE"])
    def delete_category(cid):
        c = db.session.get(Category, cid)
        if not c:
            return jsonify({"error": "not found"}), 404
        # Expenses keep a FK to their category, so a category in use can't be removed.
        if Expense.query.filter_by(category_id=cid).first():
            return jsonify({"error": "category has expenses"}), 409
        db.session.delete(c)
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/expenses", methods=["GET"])
    def list_expenses():
        page = max(request.args.get("page", 1, type=int), 1)
        per_page = min(max(request.args.get("per_page", 10, type=int), 1), 50)
        offset = (page - 1) * per_page
        q = Expense.query.filter(Expense.is_deleted == 0)
        rows = q.order_by(Expense.expense_date.desc(), Expense.id.desc()).offset(offset).limit(per_page).all()
        total = q.count()
        return jsonify(
            {
                "items": [
                    {
                        "id": e.id,
                        "category_id": e.category_id,
                        "category_name": e.category.name if e.category else "",
                        "amount": str(e.amount),
                        "description": e.description or "",
                        "expense_date": e.expense_date.isoformat() if e.expense_date else None,
                    }
                    for e in rows
                ],
                "page": page,
                "per_page": per_page,
                "total": total,
            }
        )

    @app.route("/api/expenses", methods=["POST"])
    def create_expense():
        data = request.get_json() or {}
        category_id = data.get("category_id")
        amount = data.get("amount")
        description = data.get("description") or ""
        expense_date = data.get("expense_date")
        if category_id is None or amount is None or not expense_date:
            return jsonify({"error": "category_id, amount, expense_date required"}), 400
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            return jsonify({"error": "invalid category"}), 400
        if not db.session.get(Category, category_id):
            return jsonify({"error": "invalid category"}), 400
        try:
            amount = Decimal(str(amount).strip())
        except InvalidOperation:
            return jsonify({"error": "amount must be a number"}), 400
        if not amount.is_finite() or amount <= 0:
            return jsonify({"error": "amount must be greater than 0"}), 400
        amount = amount.quantize(Decimal("0.01"))
        try:
            expense_date = datetime.strptime(str(expense_date)[:10], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "expense_date must be YYYY-MM-DD"}), 400
        e = Expense(
            category_id=category_id,
            amount=amount,
            description=str(description)[:512],
            expense_date=expense_date,
        )
        db.session.add(e)
        db.session.commit()
        return (
            jsonify(
                {
                    "id": e.id,
                    "category_id": e.category_id,
                    "amount": str(e.amount),
                    "description": e.description,
                    "expense_date": e.expense_date.isoformat(),
                }
            ),
            201,
        )

    @app.route("/api/expenses/<int:eid>", methods=["DELETE"])
    def delete_expense(eid):
        e = db.session.get(Expense, eid)
        if not e or e.is_deleted:
            return jsonify({"error": "not found"}), 404
        e.is_deleted = 1
        db.session.commit()
        return jsonify({"ok": True})

    @app.route("/api/reports/monthly", methods=["GET"])
    def report_monthly():
        year = request.args.get("year", type=int)
        month = request.args.get("month", type=int)
        today = date.today()
        if year is None:
            year = today.year
        if month is None:
            month = today.month
        if not (1 <= month <= 12) or not (1 <= year <= 9999):
            return jsonify({"error": "invalid year/month"}), 400
        start = date(year, month, 1)
        last_day = monthrange(year, month)[1]
        end = date(year, month, last_day)
        active = Expense.query.filter(
            Expense.expense_date >= start,
            Expense.expense_date <= end,
            Expense.is_deleted == 0,
        ).all()
        by_cat = {}
        for e in active:
            key = e.category_id
            if key not in by_cat:
                by_cat[key] = {"category_id": key, "category_name": e.category.name if e.category else "", "total": 0.0}
            by_cat[key]["total"] += float(e.amount)
        series = [
            {"category_name": v["category_name"], "total": v["total"]}
            for v in by_cat.values()
        ]
        return jsonify(
            {
                "year": year,
                "month": month,
                "by_category": series,
                "category_totals_for_chart": [{"name": x["category_name"], "amt": x["total"]} for x in series],
            }
        )

    @app.route("/api/reports/monthly-trend", methods=["GET"])
    def report_monthly_trend():
        now = date.today()
        buckets = []
        for i in range(5, -1, -1):
            total_months = now.year * 12 + now.month - 1 - i
            y, m = total_months // 12, total_months % 12 + 1
            start = date(y, m, 1)
            last = monthrange(y, m)[1]
            ed = date(y, m, last)
            rows = Expense.query.filter(
                Expense.expense_date >= start,
                Expense.expense_date <= ed,
                Expense.is_deleted == 0,
            ).all()
            s = sum(float(x.amount) for x in rows)
            buckets.append({"month": f"{y}-{m:02d}", "total": s})
        return jsonify({"monthly_series": buckets})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

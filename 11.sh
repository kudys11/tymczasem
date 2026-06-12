cd /opt/_docker-compose/wspolnota

cat > fix_2_8_1a_windykacja_host_container_rebuild.sh <<'SH'
#!/usr/bin/env bash
set -e

patch_file () {
  local ROOT="$1"

  python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys

ROOT = Path(sys.argv[1])

# =========================================================
# 1. Numeracja spraw: WIND -> WMB28
# =========================================================
p = ROOT / "apps/audit/models.py"
txt = p.read_text(encoding="utf-8")

txt = txt.replace(
    'self.case_number = f"WIND/{self.created_at.year}/{self.id:04d}"',
    'year = self.created_at.year if self.created_at else self.report_date.year\n            self.case_number = f"WMB28/{year}/{self.id:04d}"'
)

p.write_text(txt, encoding="utf-8")

# =========================================================
# 2. Raport spraw windykacyjnych
# =========================================================
p = ROOT / "apps/audit/admin_debt_cases_report.py"
txt = p.read_text(encoding="utf-8")

if "def _closed_statuses()" not in txt:
    txt = txt.replace(
'''def _open_statuses():
    return ("new", "demand_generated", "sent", "partially_paid")
''',
'''def _open_statuses():
    return ("new", "demand_generated", "sent", "partially_paid")


def _closed_statuses():
    return ("paid", "closed", "cancelled")


def _is_overdue(case, today=None):
    today = today or timezone.localdate()
    return bool(
        case.status not in _closed_statuses()
        and case.payment_deadline
        and case.payment_deadline < today
    )
''', 1)

txt = txt.replace(
'''        if status_filter == "open":
            qs = qs.exclude(status__in=("paid", "closed", "cancelled"))
        elif status_filter != "all":
            qs = qs.filter(status=status_filter)
''',
'''        if status_filter == "open":
            qs = qs.exclude(status__in=_closed_statuses())
        elif status_filter == "overdue":
            qs = qs.exclude(status__in=_closed_statuses()).filter(payment_deadline__lt=timezone.localdate())
        elif status_filter != "all":
            qs = qs.filter(status=status_filter)
''')

txt = txt.replace(
'''        all_cases = list(DebtCollectionCase.objects.all())
        dashboard_open = len([x for x in all_cases if x.status in _open_statuses()])
        dashboard_new = len([x for x in all_cases if x.status == "new"])
        dashboard_sent = len([x for x in all_cases if x.status == "sent"])
        dashboard_partial = len([x for x in all_cases if x.status == "partially_paid"])
        dashboard_paid = len([x for x in all_cases if x.status == "paid"])
        dashboard_amount = sum((x.arrears_amount for x in all_cases if x.status in _open_statuses()), 0)
''',
'''        all_cases = list(DebtCollectionCase.objects.all())
        open_cases = [x for x in all_cases if x.status in _open_statuses()]
        overdue_cases = [x for x in open_cases if _is_overdue(x)]

        dashboard_open = len(open_cases)
        dashboard_new = len([x for x in all_cases if x.status == "new"])
        dashboard_sent = len([x for x in all_cases if x.status == "sent"])
        dashboard_partial = len([x for x in all_cases if x.status == "partially_paid"])
        dashboard_overdue = len(overdue_cases)
        dashboard_amount = sum((x.arrears_amount for x in open_cases), 0)

        oldest_open_days = 0
        if open_cases:
            oldest = min(open_cases, key=lambda x: x.created_at)
            oldest_open_days = max((timezone.localdate() - oldest.created_at.date()).days, 0)
''')

txt = txt.replace(
'''        dashboard_open = dashboard_new = dashboard_sent = dashboard_partial = dashboard_paid = 0
        dashboard_amount = 0
''',
'''        dashboard_open = dashboard_new = dashboard_sent = dashboard_partial = dashboard_overdue = 0
        dashboard_amount = 0
        oldest_open_days = 0
''')

txt = txt.replace(
'''    def row(x, index):
        return f\\'''
        <tr>
''',
'''    def row(x, index):
        overdue_badge = '<div class="overdue">Po terminie</div>' if _is_overdue(x) else ""
        return f\\'''
        <tr>
''')

txt = txt.replace(
'''          <td>{x.get_status_display()}</td>
''',
'''          <td>{x.get_status_display()}{overdue_badge}</td>
''')

if ".overdue{{" not in txt:
    txt = txt.replace(
'''        .standard{{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}}
''',
'''        .standard{{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}}
        .overdue{{display:inline-block;margin-top:4px;border-radius:999px;padding:3px 8px;background:#fef2f2;color:#dc2626;border:1px solid #fecaca;font-size:11px;font-weight:700}}
''', 1)

if 'value="overdue"' not in txt:
    txt = txt.replace(
'''                <option value="open" {selected("open")}>Otwarte</option>
                <option value="all" {selected("all")}>Wszystkie</option>
''',
'''                <option value="open" {selected("open")}>Otwarte</option>
                <option value="overdue" {selected("overdue")}>Przeterminowane</option>
                <option value="all" {selected("all")}>Wszystkie</option>
''', 1)

txt = txt.replace(
'''        <div class="card">Spłacone<strong class="plus">{dashboard_paid}</strong></div>
        <div class="card">Kwota otwarta<strong class="minus">-{_money(dashboard_amount)}</strong></div>
''',
'''        <div class="card">Przeterminowane<strong class="minus">{dashboard_overdue}</strong></div>
        <div class="card">Najstarsza otwarta<strong>{oldest_open_days} dni</strong></div>
''')

if "Kwota otwartych spraw" not in txt:
    txt = txt.replace(
'''      <h2>Lista spraw</h2>''',
'''      <div class="grid" style="grid-template-columns:repeat(1,minmax(180px,1fr));">
        <div class="card">Kwota otwartych spraw<strong class="minus">-{_money(dashboard_amount)}</strong></div>
      </div>

      <h2>Lista spraw</h2>''', 1)

txt = txt.replace(
'''      <p class="note">Akcje zmieniają status sprawy i automatycznie zapisują odpowiednie daty oraz wpis w notatkach sprawy.</p>
''',
'''      <p class="note">Akcje zmieniają status sprawy i automatycznie zapisują odpowiednie daty oraz wpis w notatkach sprawy. Sprawy przeterminowane to otwarte sprawy, których termin płatności minął.</p>
''')

p.write_text(txt, encoding="utf-8")

print(f"OK: poprawiono {ROOT}")
PY
}

echo "== 1. Poprawiam host =="
patch_file "."

echo "== 2. Poprawiam kontener, jeśli działa =="
if docker compose ps web --status running | grep -q web; then
  docker compose exec web bash -lc "python3 - <<'PY'
from pathlib import Path

# tylko szybka kontrola i poprawka numeracji w kontenerze przed rebuildem
p = Path('/app/apps/audit/models.py')
txt = p.read_text(encoding='utf-8')
txt = txt.replace(
    'self.case_number = f\"WIND/{self.created_at.year}/{self.id:04d}\"',
    'year = self.created_at.year if self.created_at else self.report_date.year\\n            self.case_number = f\"WMB28/{year}/{self.id:04d}\"'
)
p.write_text(txt, encoding='utf-8')
print('OK: kontener poprawiony tymczasowo')
PY"
fi

echo "== 3. Rebuild =="
docker compose down
docker compose build --no-cache
docker compose up -d

echo "== 4. Czekam na start =="
sleep 15

echo "== 5. Check =="
docker compose exec web python manage.py check

echo "== 6. Uzupełniam puste/stare numery spraw =="
docker compose exec web python manage.py shell -c "
from apps.audit.models import DebtCollectionCase

for x in DebtCollectionCase.objects.all():
    if not x.case_number or x.case_number.startswith('WIND/'):
        x.case_number = ''
        x.save()

print('OK')
"

echo "== 7. Kontrola =="
docker compose exec web grep -n "WMB28" /app/apps/audit/models.py
docker compose exec web grep -n "overdue\\|Przeterminowane\\|Najstarsza otwarta" /app/apps/audit/admin_debt_cases_report.py

echo "GOTOWE: Etap 2.8.1a utrwalony na hoście i w kontenerze."
SH

chmod +x fix_2_8_1a_windykacja_host_container_rebuild.sh
./fix_2_8_1a_windykacja_host_container_rebuild.sh
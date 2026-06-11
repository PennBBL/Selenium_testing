import json
from datetime import datetime
from pathlib import Path


class SubidRegistry:
    def __init__(self, path: Path):
        self.path = path

    def load(self):
        if not self.path.exists():
            return []
        return json.loads(self.path.read_text(encoding='utf-8'))

    def save(self, records):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(records, indent=2), encoding='utf-8')

    def register_battery(self, subid: str, battery_code: str):
        records = self.load()
        records.append({
            'subid': subid,
            'battery_code': battery_code,
            'timestamp': datetime.now().isoformat(),
            'battery_status': 'started',
            'tests': [],
        })
        self.save(records)

    def mark_test_completed(self, subid: str, test_name: str, status: str, errors=None):
        records = self.load()
        for rec in records:
            if rec.get('subid') == subid:
                rec.setdefault('tests', []).append({
                    'test_name': test_name,
                    'status': status,
                    'errors': errors or [],
                    'completed_at': datetime.now().isoformat(),
                    'scraped': False,
                })
        self.save(records)

    def mark_battery_completed(self, subid: str):
        records = self.load()
        for rec in records:
            if rec.get('subid') == subid:
                rec['battery_status'] = 'completed'
                rec['completed_at'] = datetime.now().isoformat()
        self.save(records)

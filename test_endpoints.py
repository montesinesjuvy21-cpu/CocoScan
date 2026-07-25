import re
import json
from main import app

with app.test_client() as client:
    with client.session_transaction() as sess:
        sess['user_id'] = 'test-id'
        sess['user_role'] = 'lgu'
    
    res1 = client.get('/api/analytics?month=2026-07')
    res2 = client.get('/report_summary?month=2026-07')
    
    print('API SUCCESS:', res1.status_code)
    try:
        print('API DATA:', json.dumps(res1.get_json()['dashboard_payload'], indent=2))
    except Exception as e:
        print("API ERROR:", res1.text)

    html = res2.get_data(as_text=True)
    m = re.search(r'id="chart-data".*?>\s*(.*?)\s*</script>', html, re.DOTALL)
    if m:
        try:
            print('REPORT DATA:', json.dumps(json.loads(m.group(1).strip()), indent=2))
        except Exception as e:
            print("REPORT JSON ERROR:", m.group(1).strip())
    else:
        print('NO REPORT DATA FOUND')

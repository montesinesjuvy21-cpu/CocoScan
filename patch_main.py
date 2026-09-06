import re

def patch_main():
    with open(r'c:\Users\ta1yi\Desktop\CocoScan\main.py', 'r', encoding='utf-8') as f:
        content = f.read()

    new_api = """@app.route('/api/analytics')
def api_analytics():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role not in ['lgu', 'admin']:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403

    try:
        import calendar
        month_str = request.args.get('month')
        week_str = request.args.get('week')

        start_date_str = None
        end_date_str = None

        if month_str:
            try:
                year, month = map(int, month_str.split('-'))
                last_day = calendar.monthrange(year, month)[1]
                if week_str:
                    week = int(week_str)
                    start_day = (week - 1) * 7 + 1
                    end_day = min(week * 7, last_day) if week < 4 else last_day
                    start_date_str = f"{year}-{month:02d}-{start_day:02d}"
                    end_date_str = f"{year}-{month:02d}-{end_day:02d}"
                else:
                    start_date_str = f"{year}-{month:02d}-01"
                    end_date_str = f"{year}-{month:02d}-{last_day:02d}"
            except ValueError:
                pass

        query = supabase.table('reports').select('*')
        if start_date_str:
            query = query.gte('created_at', start_date_str)
        if end_date_str:
            query = query.lte('created_at', end_date_str + 'T23:59:59Z')

        reports_response = query.order('created_at', desc=True).execute()
        reports = getattr(reports_response, 'data', []) or []
        pest_reports = [r for r in reports if str(r.get('pest_type') or '').strip().lower() in ['rhinoceros beetle', 'brontispa']]
        
        status_breakdown = {
            'rhinoceros beetle': {'pending': 0, 'in_progress': 0, 'resolved': 0},
            'brontispa': {'pending': 0, 'in_progress': 0, 'resolved': 0}
        }

        for r in pest_reports:
            pest_raw = str(r.get('pest_type') or '').strip().lower()
            status = str(r.get('status') or '').strip().lower()
            
            mapped_status = 'in_progress'
            if is_pending_report_status(status):
                mapped_status = 'pending'
            elif is_resolved_report_status(status):
                mapped_status = 'resolved'
            if pest_raw in status_breakdown:
                status_breakdown[pest_raw][mapped_status] += 1
                
        # Generate chart payload using existing dashboard logic
        dashboard_payload = build_dashboard_chart_payload(pest_reports, group_by_day=bool(month_str))

        return jsonify({
            'success': True,
            'status_breakdown': status_breakdown,
            'dashboard_payload': dashboard_payload,
        })

    except Exception as e:
        logger.error(f"Error in analytics API: {str(e)}")
        return jsonify({'success': False, 'message': 'Failed to load analytics data'}), 500

@app.route('/report_summary')
def report_summary():
    user_id = session.get('user_id')
    user_role = normalize_role(session.get('user_role'))
    
    if not user_id or user_role not in ['lgu', 'admin']:
        flash("Unauthorized access.", "error")
        return redirect(url_for('login'))

    try:
        import calendar
        month_str = request.args.get('month')
        week_str = request.args.get('week')
        
        start_date_str = None
        end_date_str = None
        explanation = "This report covers all historical data across all active regions."
        
        if month_str:
            try:
                year, month = map(int, month_str.split('-'))
                last_day = calendar.monthrange(year, month)[1]
                month_name = calendar.month_name[month]
                if week_str:
                    week = int(week_str)
                    start_day = (week - 1) * 7 + 1
                    end_day = min(week * 7, last_day) if week < 4 else last_day
                    start_date_str = f"{year}-{month:02d}-{start_day:02d}"
                    end_date_str = f"{year}-{month:02d}-{end_day:02d}"
                    explanation = f"This report covers data gathered during {month_name} {year}, specifically Week {week} ({month_name} {start_day} to {end_day})."
                else:
                    start_date_str = f"{year}-{month:02d}-01"
                    end_date_str = f"{year}-{month:02d}-{last_day:02d}"
                    explanation = f"This report covers data gathered for the entire month of {month_name} {year}."
            except ValueError:
                pass

        query = supabase.table('reports').select('*')
        if start_date_str:
            query = query.gte('created_at', start_date_str)
        if end_date_str:
            query = query.lte('created_at', end_date_str + 'T23:59:59Z')

        reports_response = query.order('created_at', desc=True).execute()
        reports = getattr(reports_response, 'data', []) or []
        pest_reports = [r for r in reports if str(r.get('pest_type') or '').strip().lower() in ['rhinoceros beetle', 'brontispa']]
        
        rhino_count = sum(1 for r in pest_reports if str(r.get('pest_type') or '').strip().lower() == 'rhinoceros beetle')
        brontispa_count = sum(1 for r in pest_reports if str(r.get('pest_type') or '').strip().lower() == 'brontispa')

        pending_count = sum(1 for r in pest_reports if is_pending_report_status(str(r.get('status') or '').strip().lower()))
        resolved_count = sum(1 for r in pest_reports if is_resolved_report_status(str(r.get('status') or '').strip().lower()))
        in_progress_count = len(pest_reports) - (pending_count + resolved_count)

        location_counts = {}
        for r in pest_reports:
            loc = str(r.get('barangay') or '').strip()
            if loc:
                location_counts[loc] = location_counts.get(loc, 0) + 1
            
        locations = sorted([{'name': k, 'count': v} for k, v in location_counts.items()], key=lambda x: x['count'], reverse=True)

        from datetime import datetime
        generated_at = datetime.now().strftime("%B %d, %Y %I:%M %p")
        
        # Generate chart payload using existing dashboard logic
        dashboard_payload = build_dashboard_chart_payload(pest_reports, group_by_day=bool(month_str))

        data = {
            'explanation': explanation,
            'generated_at': generated_at,
            'total_reports': len(pest_reports),
            'rhino_count': rhino_count,
            'brontispa_count': brontispa_count,
            'pending_count': pending_count,
            'resolved_count': resolved_count,
            'in_progress_count': in_progress_count,
            'locations': locations,
            'dashboard_payload': dashboard_payload
        }

        return render_template('report_summary.html', data=data)
    except Exception as e:
        logger.error(f"Error generating report summary: {str(e)}")
        flash("Failed to generate report.", "error")
        return redirect(url_for('login'))"""

    pattern = re.compile(r"@app\.route\('/api/analytics'\).*?return redirect\(url_for\('login'\)\)", re.DOTALL)
    
    if pattern.search(content):
        new_content = pattern.sub(new_api, content)
        with open(r'c:\Users\ta1yi\Desktop\CocoScan\main.py', 'w', encoding='utf-8') as f:
            f.write(new_content)
        print("Successfully patched main.py")
    else:
        print("Pattern not found in main.py")

if __name__ == '__main__':
    patch_main()

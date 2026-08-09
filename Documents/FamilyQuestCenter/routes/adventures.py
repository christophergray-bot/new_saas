"""Family Quest Center developer documentation.

File: routes/adventures.py
Purpose: Defines Flask routes and request-handling workflows for adventures features.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from datetime import date,timedelta
from flask import Blueprint,abort,flash,redirect,render_template,request,url_for
from models.administration import log_audit
from models.family_challenges import GOAL_TYPES,create_challenge,list_challenges,set_challenge_active
from models.journeys import (
    adventure_has_assignments, assign_adventure_to_children, cancel_adventure_instance, create_adventure_with_chapters, duplicate_adventure, get_adventure,
    get_active_adventure_assignment_summaries,
    list_adventures, set_adventure_active, update_adventure_with_chapters,
)
from models.users import get_children,get_user_by_id
from services.content_packs import get_pack_source_map

parent_adventures_blueprint=Blueprint('parent_adventures',__name__,url_prefix='/parent')
child_adventures_blueprint=Blueprint('child_adventures',__name__,url_prefix='/child')


def _chapters_from_form():
    """Handle the chapters from form workflow."""
    ids=request.form.getlist('chapter_id')
    names=request.form.getlist('chapter_name')
    descriptions=request.form.getlist('chapter_description')
    chapters=[]
    for index,name in enumerate(names):
        if not name.strip():
            continue
        chapters.append({
            'id': ids[index] if index < len(ids) and ids[index].isdigit() else None,
            'name': name,
            'description': descriptions[index] if index < len(descriptions) else '',
        })
    return chapters


@parent_adventures_blueprint.route('/adventures')
def chains():
    """Handle the chains workflow."""
    rows=list_adventures(False); q=request.args.get('q','').strip().lower()
    if q: rows=[r for r in rows if q in r['name'].lower() or q in (r['description'] or '').lower()]
    return render_template('parent/adventures/chains.html',adventures=rows,children=get_children(),search_query=request.args.get('q',''),today=date.today().isoformat(),pack_sources=get_pack_source_map('adventure',[r['id'] for r in rows]),assignment_summaries=get_active_adventure_assignment_summaries())


@parent_adventures_blueprint.route('/adventures/new',methods=['GET','POST'])
def new_chain():
    """Handle the new chain workflow."""
    if request.method=='POST':
        name=request.form.get('name','').strip(); chapters=_chapters_from_form()
        if not name:
            flash('Enter an Adventure name.','error')
        elif not chapters:
            flash('Add at least one Chapter to the Adventure.','error')
        else:
            aid=create_adventure_with_chapters(name,request.form.get('description','').strip(),int(request.form.get('bonus_xp') or 100),chapters,'approval_required' in request.form)
            log_audit('adventure_created','adventure',aid,name)
            flash('Adventure and Chapters created. Assign it when you are ready.','success')
            return redirect(url_for('parent_adventures.chains'))
    return render_template('parent/adventures/chain_form.html',adventure=None)


@parent_adventures_blueprint.route('/adventures/<int:adventure_id>/edit',methods=['GET','POST'])
def edit_chain(adventure_id):
    """Handle the edit chain workflow."""
    adventure=get_adventure(adventure_id)
    if not adventure: abort(404)
    if adventure_has_assignments(adventure_id):
        return render_template('parent/adventures/locked.html', adventure=adventure)
    if request.method=='POST':
        name=request.form.get('name','').strip(); chapters=_chapters_from_form()
        if not name:
            flash('Enter an Adventure name.','error')
        elif not chapters:
            flash('Add at least one Chapter to the Adventure.','error')
        elif update_adventure_with_chapters(adventure_id,name,request.form.get('description','').strip(),int(request.form.get('bonus_xp') or 100),chapters,'approval_required' in request.form):
            log_audit('adventure_updated','adventure',adventure_id,name)
            flash('Adventure and Chapter order updated.','success')
            return redirect(url_for('parent_adventures.chains'))
        else:
            flash('This Adventure has already been assigned and cannot be changed. Duplicate it to create an editable copy.','warning')
    return render_template('parent/adventures/chain_form.html',adventure=adventure)


@parent_adventures_blueprint.post('/adventures/<int:adventure_id>/duplicate')
def duplicate_chain(adventure_id):
    """Duplicate an Adventure so future assignments can use an edited version."""
    new_id=duplicate_adventure(adventure_id)
    if not new_id:
        abort(404)
    log_audit('adventure_duplicated','adventure',new_id,f'Source Adventure {adventure_id}')
    flash('Adventure duplicated. You can now edit the copy.','success')
    return redirect(url_for('parent_adventures.edit_chain', adventure_id=new_id))


@parent_adventures_blueprint.route('/adventures/<int:adventure_id>/assign', methods=['GET','POST'])
def assign(adventure_id):
    """Display and process the Adventure assignment scheduler."""
    adventure=get_adventure(adventure_id)
    if not adventure: abort(404)
    if request.method == 'GET':
        return render_template('parent/adventures/assign.html', adventure=adventure, children=get_children(), today=date.today().isoformat())

    child_ids=[int(value) for value in request.form.getlist('child_ids') if value.isdigit()]
    if not child_ids:
        flash('Select at least one child.','error')
        return redirect(url_for('parent_adventures.chains'))
    try:
        instances=assign_adventure_to_children(adventure_id,child_ids,request.form.get('start_date') or date.today().isoformat())
    except ValueError as exc:
        flash(str(exc),'error')
        return redirect(url_for('parent_adventures.chains'))
    for iid,child_id in zip(instances,child_ids):
        log_audit('adventure_assigned','adventure_instance',iid,f'Child {child_id}')
    flash(f'Adventure assigned to {len(child_ids)} child' + ('ren.' if len(child_ids)>1 else '.'),'success')
    return redirect(url_for('parent_adventures.chains'))


@parent_adventures_blueprint.post('/adventure-assignments/<int:instance_id>/cancel')
def cancel_assignment(instance_id):
    """Cancel an active child Adventure and preserve its recorded progress."""
    if cancel_adventure_instance(instance_id):
        log_audit('adventure_cancelled','adventure_instance',instance_id,'Parent cancelled active Adventure')
        flash('Adventure cancelled. Completed Chapter history was preserved.','success')
    else:
        flash('The Adventure assignment was not active or could not be found.','warning')
    return redirect(url_for('parent_adventures.chains'))


@parent_adventures_blueprint.post('/adventures/<int:adventure_id>/toggle')
def toggle_chain(adventure_id):
    """Handle the toggle chain workflow."""
    active=request.form.get('active')=='1'; set_adventure_active(adventure_id,active); flash('Adventure restored.' if active else 'Adventure archived.','success'); return redirect(url_for('parent_adventures.chains'))


@parent_adventures_blueprint.route('/challenges',methods=['GET','POST'])
def challenges():
    """Handle the challenges workflow."""
    if request.method=='POST':
        cid=create_challenge(request.form['name'].strip(),request.form.get('description','').strip(),request.form['goal_type'],int(request.form['target_value']),request.form['start_date'],request.form['end_date'],request.form.get('reward_text','').strip())
        log_audit('family_challenge_created','family_challenge',cid,request.form['name']); flash('Family challenge created.','success'); return redirect(url_for('parent_adventures.challenges'))
    rows=list_challenges(False); search=request.args.get('q','').strip().lower()
    if search: rows=[row for row in rows if search in row['name'].lower() or search in (row['description'] or '').lower()]
    return render_template('parent/adventures/challenges.html',challenges=rows,goal_types=GOAL_TYPES,today=date.today().isoformat(),default_end=(date.today()+timedelta(days=30)).isoformat(),search_query=request.args.get('q',''))


@parent_adventures_blueprint.post('/challenges/<int:challenge_id>/toggle')
def toggle_challenge(challenge_id):
    """Handle the toggle challenge workflow."""
    active=request.form.get('active')=='1'; set_challenge_active(challenge_id,active); flash('Family challenge restored.' if active else 'Family challenge archived.','success'); return redirect(url_for('parent_adventures.challenges'))


@child_adventures_blueprint.route('/<int:user_id>/adventures')
def child_chains(user_id):
    """Handle the child chains workflow."""
    child=get_user_by_id(user_id)
    if not child or child['role']!='child': abort(404)
    from models.journeys import current_child_journeys, list_child_adventure_celebrations
    return render_template('child/adventures.html',child=child,chains=current_child_journeys(user_id),celebrations=list_child_adventure_celebrations(user_id))


@child_adventures_blueprint.route('/<int:user_id>/family-challenges')
def child_challenges(user_id):
    """Handle the child challenges workflow."""
    child=get_user_by_id(user_id)
    if not child or child['role']!='child': abort(404)
    return render_template('child/family_challenges.html',child=child,challenges=list_challenges())

# Factory Floor Behavior Spec v1

## Purpose
The Factory Floor is a live visual representation of AI work. Workers visibly operate inside their assigned division, build a package as work progresses, deliver that package to a division manager, and managers route approved packages onward by conveyor or inter-zone signal path.

## Agent classes
- **worker**: remains inside its home division; may move around the division while working; cannot independently cross approval boundaries.
- **manager**: reviews worker packages; may route packages to other divisions or approval areas allowed by its authority.
- **overseer**: system-level authority for exceptional escalation, safety, or high-risk approval.

## Package lifecycle
`drafting -> ready_for_manager -> manager_review -> approved -> in_transfer -> awaiting_external_approval -> completed`

A package may enter `blocked` from any nonterminal state.

## Transfer rules
- **local_conveyor**: movement within a division or between adjacent work areas.
- **signal_route**: long-distance or cross-approval transfer. The route visibly lights, flickers, and animates while active.
- **escalation_route**: high-authority path for safety, funding, research escalation, or exceptional approval.

## Alert model
Every blocking alert carries:
- origin division
- originating agent
- package / product
- approvals already completed
- next required action
- intended objective
- severity

Alerts must be suitable for action from desktop or phone.

## Visual behavior
Workers move only within their home division. Active workers gradually display a visible package. Managers are visually distinct and can leave their home area when routing an approved package. Active signal lines use typed colors and animation. Blocked managers display a yellow warning triangle; hard stops display a red stop indicator.

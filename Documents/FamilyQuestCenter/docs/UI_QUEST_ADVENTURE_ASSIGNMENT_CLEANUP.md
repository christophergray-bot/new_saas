# Quest and Adventure Assignment Interface Cleanup

Implemented 2026-08-02.

- Each Quest and Adventure card now contains its own Currently Assigned section.
- Assigned children are listed as collapsed rows using native HTML details/summary controls.
- Expanding a Quest child displays Edit, Pause/Resume, and Unassign controls.
- Expanding an Adventure child displays progress, start date, and Cancel Adventure.
- Card-level Edit, Assign, and Archive/Restore controls align at the bottom-right on wide screens and scale/wrap on smaller screens.
- Quest archive/restore now uses a CSRF-protected POST form.
- Existing tenant scoping and server-side assignment actions were preserved.


## Follow-up alignment update

Quest and Adventure card-level Edit, Assign, and Archive/Restore controls now appear directly below the card's Currently Assigned section and align to the left. Responsive wrapping and mobile stacking remain enabled.

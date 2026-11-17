// Select the installed model once; never override a user's explicit selection.
export function createAsrChoice(select) {
  let chosen = false;
  select.addEventListener('change', () => { chosen = true; });
  return status => {
    if (chosen || status?.state !== 'ready') return;
    if ([...select.options].some(option => option.value === status.defaultModel)) {
      select.value = status.defaultModel;
      chosen = true;
    }
  };
}

// The existing API owns token deltas. Cached input/reasoning are subsets, not additions.
export function usageView(value, hours) {
  if (![24,168,720].includes(hours) || !value || value.ok !== true || value.hours !== hours ||
      !['ok','partial','no_data'].includes(value.status) || !Array.isArray(value.items) ||
      !Number.isSafeInteger(value.window?.after_ms) || !Number.isSafeInteger(value.window?.before_ms)) throw Error('Invalid usage projection');
  const points = value.items.map(row => {
    if (!Number.isSafeInteger(row.bucket_ms) || row.bucket_ms < value.window.after_ms || row.bucket_ms > value.window.before_ms ||
        !Number.isSafeInteger(row.delta_tokens) || row.delta_tokens < 0) throw Error('Invalid token observation');
    return {at:row.bucket_ms,tokens:row.delta_tokens};
  });
  if (points.some((p,i)=>i && p.at<=points[i-1].at)) throw Error('Conflicting token observations');
  const total=points.reduce((sum,p)=>sum+p.tokens,0);
  if (!Number.isSafeInteger(total) || points.length && total!==value.total_tokens || value.status==='no_data' && points.length) throw Error('Token total mismatch');
  return {total:points.length?total:null,points,status:points.length?value.status:'no_data',coverage:value.coverage||{},window:value.window};
}

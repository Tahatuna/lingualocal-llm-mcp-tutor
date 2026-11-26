// Looks words up in the dictionaries built into macOS (Dictionary.app) and prints JSON:
//   osascript -l JavaScript dictionary.js '<json: {"words": [...], "dicts": ["New Oxford American", "Oxford Turkish"]}>'
// -> {"<word>": {"<dict name>": ["<entry html>", ...]}}
// DCSCopyRecordsForSearchString is not a public API; it returns every homograph (bank 1, bank 2), which the public
// DCSCopyTextDefinition does not. If it ever disappears, the service falls back to its other sources.
ObjC.import('CoreServices');
ObjC.bindFunction('DCSGetActiveDictionaries', ['id', []]);
ObjC.bindFunction('DCSCopyRecordsForSearchString', ['id', ['id', 'id', 'void*', 'void*']]);
ObjC.bindFunction('DCSRecordCopyData', ['id', ['id', 'long']]);
ObjC.bindFunction('DCSDictionaryGetName', ['id', ['id']]);
function run(argv) {
  const req = JSON.parse(argv[0]);
  const dicts = $.DCSGetActiveDictionaries(), use = [];
  for (let i = 0; i < dicts.count; i++) {
    const d = dicts.objectAtIndex(i), name = ObjC.unwrap($.DCSDictionaryGetName(d));
    const key = req.dicts.find((p) => name.startsWith(p));
    if (key) use.push([key, d]);
  }
  const out = {};
  for (const w of req.words) {
    out[w] = {};
    for (const [key, d] of use) {
      const recs = $.DCSCopyRecordsForSearchString(d, $(w), null, null), list = [];
      for (let j = 0; recs && !recs.isNil() && j < recs.count && j < 8; j++) {
        list.push(ObjC.unwrap($.DCSRecordCopyData(recs.objectAtIndex(j), 0)));
      }
      out[w][key] = list;
    }
  }
  return JSON.stringify(out);
}

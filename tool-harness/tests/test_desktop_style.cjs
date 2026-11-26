const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../desktop/plugin.js'), 'utf8')
  .replace(/^import .*;\s*$/gm, '')
  .replace('export function register', 'function register')
  .replace('export default {', 'const defaultExport = {')
  + '\nglobalThis.probe = { StatusProbe };';

for (const [phase, cli, expected, dot] of [
  ['active', 'found', 'CommandPLUG · CLI found', 'var(--ui-green)'],
  ['inactive', 'unknown', 'CommandPLUG: unconfirmed', 'var(--ui-yellow)'],
  ['pending', 'unknown', 'CommandPLUG: checking', 'var(--ui-yellow)'],
  ['offline', 'unknown', 'CommandPLUG: offline', 'var(--ui-text-quaternary)'],
]) {
  let state = 0;
  const context = {
    jsx: (type, props) => ({ type, props }),
    useState: () => [state++ === 0 ? phase : cli, () => {}],
    useEffect: () => {},
    host: {}, useValue: () => {},
  };
  vm.runInNewContext(source, context);
  const node = context.probe.StatusProbe({ open: phase !== 'offline', profile: 'default' });
  assert.equal(node.props.children[1].props.children, expected);
  assert.equal(node.props.children[0].props.style.backgroundColor, dot);
  assert.equal(node.props.style.color, 'var(--ui-text-secondary)');
  assert.equal(node.props.style.font, 'inherit');
  assert.equal(node.props.style.backgroundColor, undefined);
  assert.equal(node.props.style.border, undefined);
  assert.equal(node.props.role, 'status');
}
console.log('desktop status style: all four states passed');

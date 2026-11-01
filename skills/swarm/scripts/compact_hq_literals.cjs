// Pool repeated string expressions in the fixed HQ modules before bundling.
// The caller pins Acorn and records these source files in the bundle identity.
const fs = require('node:fs');
const path = require('node:path');
const acorn = require(process.argv[2]);
const source = process.argv[3];
const output = process.argv[4];
const modules = ['swarm-projects-bootstrap.mjs', 'swarm-settings.js', 'swarm-velocity.mjs', 'swarm-projects.mjs', 'swarm-usage.mjs'];
for (const file of modules) {
  const text = fs.readFileSync(path.join(source, file), 'utf8');
  if (text.includes('__swarmProfileConst')) throw Error('HQ literal identifier already exists');
  const ast = acorn.parse(text, {ecmaVersion: 'latest', sourceType: 'module'});
  const literals = new Map();
  function visit(node, parent) {
    if (!node || !node.type) return;
    if (node.type === 'WithStatement' || (node.type === 'CallExpression' && node.callee.type === 'Identifier' && node.callee.name === 'eval')) throw Error('HQ literal scope cannot be proved');
    if (node.type === 'Literal' && typeof node.value === 'string' && node.value.length >= 5 && parent &&
        !['ImportDeclaration', 'ImportExpression', 'ImportSpecifier', 'ImportAttribute', 'ExportNamedDeclaration', 'ExportAllDeclaration', 'ExportSpecifier', 'Property', 'PropertyDefinition', 'MethodDefinition'].includes(parent.type) &&
        !(parent.type === 'ExpressionStatement' && parent.directive)) {
      const matches = literals.get(node.value) || [];
      matches.push(node);
      literals.set(node.value, matches);
    }
    for (const value of Object.values(node)) {
      if (Array.isArray(value)) value.forEach(child => visit(child, node));
      else if (value && value.type) visit(value, node);
    }
  }
  visit(ast, null);
  const declarations = [], edits = [];
  for (const [value, matches] of literals) {
    if (matches.length < 2) continue;
    const name = '__swarmProfileConst' + declarations.length;
    declarations.push(`const ${name}=${JSON.stringify(value)};`);
    for (const node of matches) edits.push({start: node.start, end: node.end, name});
  }
  edits.sort((a, b) => b.start - a.start);
  let result = text;
  for (const edit of edits) result = result.slice(0, edit.start) + edit.name + result.slice(edit.end);
  fs.writeFileSync(path.join(output, file), declarations.join('\n') + '\n' + result, 'utf8');
}
fs.copyFileSync(path.join(source, 'swarm-hq-bootstrap.mjs'), path.join(output, 'swarm-hq-bootstrap.mjs'));

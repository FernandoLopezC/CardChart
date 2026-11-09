const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const {test} = require('node:test');
const assert = require('node:assert/strict');
class Element { constructor() { this.listeners = {}; this.dataset = {}; this.attrs = {}; } addEventListener(k, f) { this.listeners[k] = f; } setAttribute(k,v) { this.attrs[k] = v; } removeAttribute(k) { delete this.attrs[k]; } }
test('inspector restores focus and switches exact version price and link', () => {
 const button = new Element(), dialog = new Element(), close = new Element(), select = new Element(), price = new Element(), link = new Element();
 button.dataset.openDialog = 'one'; button.focus = () => { button.focused = true; };
 dialog.showModal = () => { dialog.open = true; }; dialog.close = () => dialog.listeners.close();
 dialog.querySelector = s => ({'[data-close-dialog]':close,'[data-version]':select,'[data-price]':price,'[data-market-link]':link})[s];
 select.selectedOptions = [{dataset:{gbp:'3.20',eur:'4.00',cardmarketUrl:'https://example.test/card'}}];
 const window = {scrollY:42,scrollX:0,scrollTo(x,y){this.restored=y;}};
 runInNewContext(readFileSync('cardchart/static/collector.js','utf8'), {document:{querySelectorAll:s=>s === "[data-open-dialog]" ? [button] : [],getElementById:()=>dialog},window});
 button.listeners.click(); assert.equal(dialog.open,true); select.listeners.change(); assert.equal(price.textContent,'≈ £3.20 (€4.00)'); assert.equal(link.href,'https://example.test/card');
 select.selectedOptions = [{dataset:{}}]; select.listeners.change(); assert.equal(price.textContent,'Price unavailable'); assert.equal(link.hidden,true);
 close.listeners.click(); assert.equal(window.restored,42); assert.equal(button.focused,true);
});

test('failed goal covers reveal a labelled fallback, including cached failures', () => {
 const failed = new Element(), cached = new Element();
 failed.nextElementSibling = {hidden:true}; cached.nextElementSibling = {hidden:true};
 cached.complete = true; cached.naturalWidth = 0;
 runInNewContext(readFileSync('cardchart/static/collector.js','utf8'), {document:{querySelectorAll:s=>s === '[data-goal-cover]' ? [failed,cached] : []}});
 assert.equal(cached.hidden,true); assert.equal(cached.nextElementSibling.hidden,false);
 failed.listeners.error(); assert.equal(failed.hidden,true); assert.equal(failed.nextElementSibling.hidden,false);
});

test('failed card artwork has a readable unavailable state', () => {
 const image = new Element();
 image.after = element => { image.fallback = element; };
 runInNewContext(readFileSync('cardchart/static/collector.js','utf8'), {document:{querySelectorAll:s=>s === '.collector-art img' ? [image] : [],createElement:()=>({})}});
 image.listeners.error();
 assert.equal(image.hidden,true);
 assert.equal(image.fallback.textContent,'Image unavailable');
});

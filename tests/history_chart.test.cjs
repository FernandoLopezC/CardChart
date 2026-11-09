const {readFileSync} = require('node:fs');
const {runInNewContext} = require('node:vm');
const {test} = require('node:test');
const assert = require('node:assert/strict');
class Element { constructor(){this.listeners={};this.attrs={};this.children=[];} addEventListener(k,f){this.listeners[k]=f;} setAttribute(k,v){this.attrs[k]=v;} append(child){this.children.push(child);} getBoundingClientRect(){return {left:100,width:400};} }
test('history uses dates, keeps unavailable gaps, and supports pointer and keyboard',()=>{
 const svg=new Element(),lines=new Element(),grid=new Element(),cursor=new Element(),marker=new Element(),readout=new Element(),high=new Element(),low=new Element();
 const points=[{observed_at:'2026-01-01',gbp:'10.00',priced_count:1,inventory_count:2,quantity:2},{observed_at:'2026-01-02',gbp:null,priced_count:0,inventory_count:2,quantity:2},{observed_at:'2026-01-11',gbp:'20.00',priced_count:2,inventory_count:2,quantity:2}];
 const chart={dataset:{points:JSON.stringify(points)},querySelector:s=>({'svg':svg,'.chart-lines':lines,'.chart-grid':grid,'.chart-cursor':cursor,'.chart-marker':marker,'.chart-readout':readout,'[data-chart-high]':high,'[data-chart-low]':low})[s]};
 runInNewContext(readFileSync('cardchart/static/history-chart.js','utf8'),{document:{querySelectorAll:()=>[chart],createElementNS:()=>new Element()}});
 assert.equal(lines.children.length,0,'unavailable observation breaks the line'); assert.equal(high.textContent,'\u00a320.00');
 svg.listeners.pointerdown({clientX:140}); assert.match(readout.textContent,/2026-01-02.*Value unavailable/); assert.equal(marker.attrs.visibility,'hidden');
 const key = k => {let prevented=false;svg.listeners.keydown({key:k,preventDefault(){prevented=true;}});assert.equal(prevented,true);};
 key('ArrowLeft'); assert.match(readout.textContent,/2026-01-01.*\u00a310.00/); key('End'); assert.match(readout.textContent,/2026-01-11.*Period change \u00a310.00/); key('Home'); assert.match(readout.textContent,/2026-01-01/); key('ArrowRight'); assert.match(readout.textContent,/2026-01-02/);
});

// Offline DOM QA. Supply --jsdom <installed-jsdom-package-path> when not on NODE_PATH.
const fs=require('fs'),path=require('path'),assert=require('assert');
const arg=process.argv.indexOf('--jsdom');const {JSDOM,VirtualConsole}=require(arg>=0?path.resolve(process.argv[arg+1]):'jsdom');
const root=__dirname,out=path.join(root,'results'),errors=[],checks=[],vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(String(e)));
const dom=new JSDOM(fs.readFileSync(path.join(out,'report.html'),'utf8'),{runScripts:'dangerously',url:'https://offline.invalid/',virtualConsole:vc});const w=dom.window,d=w.document,$=id=>d.getElementById(id);
function check(name,b){assert(b,name);checks.push(name)}function change(id,v){$(id).value=String(v);$(id).dispatchEvent(new w.Event('change'))}
for(const design of ['all_available','strict_common','lowland_available'])for(const factor of ['coast','region'])for(const variable of ['Tmax','Tmin'])for(let lead=1;lead<=9;lead++){
 change('design',design);change('factor',factor);change('variable',variable);change('lead',lead);
 const key=[design,factor,variable,lead].join('/');
 check('all station rows '+key,$('stations').querySelectorAll('tbody tr').length===(design==='lowland_available'?29:30));
 check('correct category count '+key,$('groups').querySelectorAll('tbody tr').length===(factor==='region'?4:3));
 check('37 station points retained '+key,$('map').querySelectorAll('[data-code]').length===37);
 check('no missing rendered numbers '+key,!/NaN|undefined/.test($('groups').innerHTML+$('stations').innerHTML));
 if(factor==='region')check('islands separate '+key,$('groups').textContent.includes('離島區'));
}
change('design','all_available');change('factor','region');
for(const code of ['CCH','NGP','PEN','WGL']){$('map').querySelector(`[data-code="${code}"]`).dispatchEvent(new w.MouseEvent('click'));check('islands map click '+code,$('detail').textContent.includes('離島區')&&$('detail').textContent.includes(code))}
for(const code of ['TC','TMS']){w.eval(`choose('${code}')`);check('excluded remains unscored '+code,$('detail').textContent.includes('未加入'))}
change('design','lowland_available');w.eval("choose('NGP')");check('NGP excluded only in lowland sensitivity',$('detail').textContent.includes('未加入'));
let links=0;for(const el of d.querySelectorAll('[src],[href]')){const ref=el.getAttribute('src')||el.getAttribute('href');if(/^https?:/.test(ref))continue;check('local link '+ref,fs.existsSync(path.resolve(out,ref)));links++}
check('no DOM exceptions',errors.length===0);
fs.writeFileSync(path.join(out,'viewer_verification.json'),JSON.stringify({passed:true,checks:checks.length,items:checks,local_links:links,browser_visual_verification:false,method:'JSDOM offline execution; all 3 data designs x 2 factors x 2 variables x 9 leads; all station rows and four independent Island selections.'},null,2));
change('design','all_available');change('variable','Tmax');change('lead',3);w.eval("choose('NGP')");const svg=$('map');svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width','960');svg.setAttribute('height','680');fs.writeFileSync(path.join(out,'map_preview.svg'),svg.outerHTML);
console.log('PASS',checks.length,'offline viewer checks.');w.close();

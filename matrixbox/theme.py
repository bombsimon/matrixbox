CSS = """
:root{--bg:#08080f;--surface:#111118;--surface2:#1c1c2a;--surface3:#26263a;--accent:#7c6fff;--accent2:#00d4ff;--text:#eeeef5;--muted:#7070a0;--border:rgba(120,120,255,.1);--r:10px;--r-lg:16px;--shadow:0 4px 24px rgba(0,0,0,.5)}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,-apple-system,sans-serif;min-height:100vh;padding-bottom:40px}
.navbar{position:sticky;top:0;z-index:100;background:rgba(8,8,15,.85);border-bottom:1px solid var(--border);padding:0 14px;display:flex;align-items:center;height:46px;gap:4px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)}
.nav-brand{font-weight:800;font-size:.9rem;color:#fff;margin-right:6px;text-decoration:none;letter-spacing:-.2px}
.brand-yellow{color:#f0c800;font-weight:900}
.nav-title{font-weight:600;font-size:.9rem;color:var(--text);flex:1;padding-left:4px}
.nav-spacer{flex:1}
.nav-info{color:var(--muted);font-size:.72rem;letter-spacing:.2px;text-align:right;line-height:1.4}
.nav-version{display:block;font-size:.62rem;opacity:.7}
.nav-stats{display:block;font-size:.62rem;opacity:.7}
.update-dot{display:inline-block;width:6px;height:6px;margin-left:4px;border-radius:50%;background:#f5e040;vertical-align:middle}
.hamburger-wrap{position:relative;margin-left:4px}
.hamburger-toggle{background:none;font-family:inherit;cursor:pointer;color:var(--muted);font-size:1.1rem;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:8px;border:1px solid var(--border)}
.hamburger-toggle:hover{color:var(--text);border-color:var(--accent)}
.hamburger-menu{position:absolute;top:40px;right:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);box-shadow:var(--shadow);min-width:190px;z-index:200;overflow:hidden;display:none}
.hamburger-menu.open{display:block}
.hamburger-menu a,.hamburger-menu button{display:flex;align-items:center;gap:10px;padding:12px 16px;color:var(--text);text-decoration:none;font-size:.85rem;font-weight:500;width:100%;text-align:left;background:none;border:none;border-bottom:1px solid var(--border);cursor:pointer;font-family:inherit}
.hamburger-menu a:last-child,.hamburger-menu button:last-child{border-bottom:none}
.hamburger-menu a:hover,.hamburger-menu button:hover{background:var(--surface2)}
.hamburger-menu .hm-icon{font-size:1rem;width:20px;text-align:center;flex-shrink:0}
.sig{display:flex;align-items:center;gap:2px;margin:0 6px}
.sig i{display:block;width:5px;height:5px;background:rgba(112,112,160,.3);border-radius:1px}
.sig i.on{background:#00c853}
.nav-x{background:none;font-family:inherit;cursor:pointer;color:var(--muted);font-size:1rem;font-weight:700;text-decoration:none;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:8px;border:1px solid var(--border);margin-left:4px}
.nav-x:hover{color:#ff6060;border-color:rgba(255,96,96,.4);background:rgba(255,96,96,.08)}
.nav-led{background:none;font-family:inherit;color:var(--muted);font-size:.85rem;width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:8px;border:1px solid var(--border);transition:color .15s,border-color .15s,background .15s;margin-left:4px;cursor:pointer}
.nav-led:hover{color:#ffd060;border-color:rgba(255,208,96,.4);background:rgba(255,208,96,.08)}
.nav-led.led-off{color:#ff4040;border-color:rgba(255,64,64,.35);background:rgba(255,64,64,.06)}
.page{max-width:480px;margin:0 auto;padding:16px 14px}
.logo{text-align:center;padding:26px 0 18px}
.logo h1{font-size:1.8rem;font-weight:800;color:#fff;letter-spacing:-.5px}
.logo p{color:var(--muted);font-size:.82rem;margin-top:6px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r-lg);padding:16px;margin-bottom:10px;box-shadow:var(--shadow)}
.section-title{font-size:.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:1.4px;font-weight:700;margin-bottom:12px;padding-bottom:8px;border-bottom:1px solid var(--border)}
.app-item{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px 10px;padding:10px 0;border-bottom:1px solid var(--border)}
.app-item:last-child{border-bottom:none}
.app-item-main{display:flex;flex-direction:column;gap:2px;min-width:0}
.app-name{font-size:.92rem;font-weight:500;text-transform:capitalize;color:var(--text)}
.app-meta{font-size:.7rem;color:var(--muted)}
.app-actions{display:flex;align-items:center;flex-wrap:wrap;gap:6px}
.flash-stat{font-size:.75rem;color:var(--muted);margin-bottom:10px}
.catalog-status{font-size:.75rem;color:var(--muted);text-align:center;margin-top:10px;min-height:14px}
label{display:block;font-size:.67rem;color:var(--muted);text-transform:uppercase;letter-spacing:.9px;margin:13px 0 5px;font-weight:600}
input[type="text"],input[type="password"],select,textarea{width:100%;background:var(--surface2);border:1.5px solid var(--border);border-radius:var(--r);padding:10px 12px;color:var(--text);font-size:.93rem;outline:none;-webkit-appearance:none}
input[type="text"]:focus,input[type="password"]:focus,select:focus,textarea:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(124,111,255,.15)}
textarea{font-family:inherit}
.pw-toggle{position:absolute;right:6px;top:50%;transform:translateY(-50%);background:none;border:none;cursor:pointer;font-size:1rem;padding:4px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:9px 18px;border:none;border-radius:var(--r);font-size:.86rem;line-height:1;font-weight:600;cursor:pointer;color:#111;background:linear-gradient(135deg,#c8a800,#f5e040);text-decoration:none;box-shadow:0 2px 12px rgba(200,168,0,.35)}
.btn:hover{opacity:.88}
.btn-sm{padding:6px 12px;font-size:.8rem}
.btn-full{width:100%;padding:12px;font-size:.93rem;margin-top:10px}
.btn-danger{background:linear-gradient(135deg,#e03c3c,#ff6060);color:#fff}
.btn-save{background:linear-gradient(135deg,#1e8a4c,#2ecc71);color:#fff}
.btn-ghost{background:var(--surface2);border:1px solid var(--border);color:var(--text);box-shadow:none}
.btn-ghost:hover{border-color:var(--accent);background:var(--surface3)}
.range-wrap{display:flex;align-items:center;gap:10px;margin-top:5px}
.range-wrap input[type="range"]{flex:1;-webkit-appearance:none;appearance:none;height:5px;border-radius:3px;background:var(--surface3);outline:none}
.range-wrap input[type="range"]::-webkit-slider-thumb{-webkit-appearance:none;width:18px;height:18px;border-radius:50%;background:linear-gradient(135deg,#c8a800,#f5e040);cursor:pointer;border:2px solid var(--bg);box-shadow:0 2px 8px rgba(232,150,14,.4)}
.range-wrap input[type="range"]::-moz-range-thumb{width:18px;height:18px;border-radius:50%;background:linear-gradient(135deg,#c8a800,#f5e040);cursor:pointer;border:2px solid var(--bg);box-shadow:0 2px 8px rgba(232,150,14,.4)}
.range-val{min-width:34px;text-align:center;font-size:.85rem;font-weight:700;color:#f0c800;background:var(--surface2);padding:3px 7px;border-radius:7px}
.switch-row{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:13px 0 5px}
.switch-row span{font-size:.85rem;color:var(--text);font-weight:500}
.switch{position:relative;display:inline-block;width:42px;height:24px;flex-shrink:0}
.switch input{opacity:0;width:0;height:0;position:absolute}
.switch .slider{position:absolute;inset:0;background:var(--surface3);border-radius:24px;cursor:pointer;transition:background .15s;border:1px solid var(--border)}
.switch .slider:before{content:"";position:absolute;height:18px;width:18px;left:2px;top:2px;background:#fff;border-radius:50%;transition:transform .15s;box-shadow:0 1px 3px rgba(0,0,0,.4)}
.switch input:checked+.slider{background:linear-gradient(135deg,var(--accent),var(--accent2));border-color:transparent}
.switch input:checked+.slider:before{transform:translateX(18px)}
.collapsible-header{display:flex;align-items:center;justify-content:space-between;cursor:pointer;user-select:none;font-size:.85rem;font-weight:600;color:var(--text)}
.collapsible-header .caret{font-size:.7rem;color:var(--muted);transition:transform .15s}
.collapsible-header.open .caret{transform:rotate(90deg)}
.seg{display:flex;background:var(--surface2);border-radius:var(--r);padding:3px;gap:2px;border:1px solid var(--border)}
.seg button{flex:1;padding:6px 10px;border:none;border-radius:8px;font-size:.8rem;font-weight:600;cursor:pointer;background:none;color:var(--muted)}
.seg button.on{background:linear-gradient(135deg,var(--accent),var(--accent2));color:#fff;box-shadow:0 2px 8px rgba(124,111,255,.3)}
.back-btn{display:inline-flex;align-items:center;gap:6px;color:var(--text);text-decoration:none;font-size:.93rem;font-weight:600;padding:11px 18px;border-radius:var(--r);background:var(--surface);border:1px solid var(--border);margin-top:14px}
.back-btn:hover{color:#fff;border-color:var(--accent)}
.error-msg{color:#ff7070;font-size:.82rem;margin-top:10px;text-align:center}
"""

FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
    '<rect width="32" height="32" rx="6" fill="#111118"/>'
    '<rect x="6" y="13" width="4" height="9" fill="#f5e040"/>'
    '<rect x="14" y="7" width="4" height="15" fill="#7c6fff"/>'
    '<rect x="22" y="16" width="4" height="6" fill="#00d4ff"/>'
    "</svg>"
)

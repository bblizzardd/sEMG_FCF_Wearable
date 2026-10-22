/**
 * tabs.mjs – Chuyển giữa tab "Trực tiếp" và "Xem lại dữ liệu đã ghi" (#live / #review trên URL).
 */
const TABS = ['live', 'review'];

function showTab(name, updateHash = true) {
  if (!TABS.includes(name)) name = 'live';
  for (const tab of TABS) {
    document.getElementById('tab-' + tab).hidden = tab !== name;
  }
  for (const node of document.querySelectorAll('[data-tab]')) {
    const active = node.dataset.tab === name;
    node.classList.toggle('active', active);
    if (node.getAttribute('role') === 'tab') node.setAttribute('aria-selected', String(active));
  }
  if (updateHash && location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
  // Canvas vừa hiện ra mới có kích thước thật: báo các module vẽ lại
  window.dispatchEvent(new CustomEvent('tab-shown', {detail: name}));
}

for (const node of document.querySelectorAll('[data-tab]')) {
  node.addEventListener('click', event => {
    event.preventDefault();
    showTab(node.dataset.tab);
  });
}
window.addEventListener('hashchange', () => showTab(location.hash.slice(1), false));
window.showTab = showTab;
showTab(location.hash.slice(1) || 'live', false);

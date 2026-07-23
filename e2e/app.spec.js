const { test, expect } = require('@playwright/test');

const MAIN_PAGES = [
  '/app',
  '/app/generate',
  '/app/rewrite',
  '/app/products',
  '/app/creators',
  '/app/templates',
  '/app/history',
  '/app/import',
  '/app/search',
  '/app/ai-config',
  '/app/operations',
  '/app/api-connections',
];

const TOOL_PAGES = MAIN_PAGES;

const WORKSPACE_PRODUCT = {
  id: 42,
  name: '奶冻粉',
  category: '烘焙调味',
  price: 88,
  pending_fields: [],
  selling_point_count: 2,
  selling_point_summary: '[稳定]冷藏不易出水；[效率]操作简单',
  selling_points: [
    { point_type: '稳定', content: '冷藏不易出水', priority: 1 },
    { point_type: '效率', content: '操作简单', priority: 2 },
  ],
};

const WORKSPACE_BREAKDOWN = {
  source: 'ai',
  generation_rationale: '先指出赶单时的稳定性问题，再用产品表现收束。',
  target_audience: '需要稳定出品的烘焙门店',
  structure: Array.from({ length: 12 }, (_, index) => ({
    stage: `阶段${index + 1}`,
    copy_excerpt: '奶冻冷藏后依然稳定',
    purpose: '强化产品稳定性',
  })),
  core_selling_points: ['冷藏稳定', '操作简单'],
  conversion_triggers: [{ copy_excerpt: '赶单也不慌', reason: '降低出品风险' }],
  optimization_suggestions: [{ issue: '开头可更直接', recommendation: '先展示失败场景' }],
  shooting_notes: ['拍摄冷藏后的奶冻状态'],
  shot_requirements: Array.from({ length: 8 }, (_, index) => ({
    script_segment: `镜头${index + 1}`,
    shot_type: '近景',
    subject_action: '展示奶冻切面',
    visual_requirement: '保持画面清晰明亮',
  })),
};

async function mockGenerateWorkspaceApis(page, options = {}) {
  let jobReads = 0;
  const result = {
    id: 77,
    product_name: '奶冻粉',
    video_type: '成本低',
    script_content: '初始生成脚本',
    source_script_title: '参考脚本',
    source_script_content: '参考脚本正文',
    source_script_source: 'facai',
    template_name: '成本低模板',
    source_match_query: '奶冻粉',
  };
  await page.route('**/api/products/categories', route => route.fulfill({ json: ['烘焙调味'] }));
  await page.route(/\/api\/products\/page(?:\?.*)?$/, route => route.fulfill({
    json: { items: [WORKSPACE_PRODUCT], total: 1, page: 1, per_page: 100, total_pages: 1 },
  }));
  await page.route('**/api/products/42', route => route.fulfill({ json: WORKSPACE_PRODUCT }));
  await page.route('**/api/scripts/generate/jobs', route => route.fulfill({
    status: 202,
    json: { job: { public_id: 'workspace-job' } },
  }));
  await page.route('**/api/jobs/workspace-job', route => {
    jobReads += 1;
    const runningFirst = options.runningFirst && jobReads <= 2;
    return route.fulfill({
      json: {
        public_id: 'workspace-job',
        job_type: 'ai.scripts.generate',
        status: runningFirst ? 'running' : 'succeeded',
        message: runningFirst ? '生成中' : '已完成',
        result: runningFirst ? null : result,
      },
    });
  });
  await page.route(/\/api\/jobs(?:\?.*)?$/, route => route.fulfill({ json: { items: [] } }));
  await page.route('**/api/scripts/history/77', route => route.fulfill({
    json: { id: 77, product_id: 42, script_content: result.script_content, video_type: result.video_type },
  }));
  await page.route('**/api/scripts/content-breakdown', route => route.fulfill({ json: WORKSPACE_BREAKDOWN }));
}

test('all main pages render without console errors', async ({ page }) => {
  await page.route('**/api/integrations/providers', route => route.fulfill({
    json: { providers: [] },
  }));
  await page.route(/\/api\/integrations\/connections(?:\?.*)?$/, route => route.fulfill({
    json: { connections: [] },
  }));
  await page.route(/\/api\/integrations\/sync-runs(?:\?.*)?$/, route => route.fulfill({
    json: { items: [], total: 0, page: 1, per_page: 50, total_pages: 1 },
  }));

  const errors = [];
  page.on('console', message => {
    if (message.type() === 'error') {
      const location = message.location();
      errors.push(`${message.text()} @ ${location.url || 'unknown'}`);
    }
  });
  page.on('pageerror', error => errors.push(error.message));

  for (const path of MAIN_PAGES) {
    const response = await page.goto(path, { waitUntil: 'domcontentloaded' });
    expect(response && response.ok(), `${path} should return 2xx`).toBeTruthy();
    await page.waitForTimeout(150);
  }

  expect(errors).toEqual([]);
});

test('mobile AI work opens with chat visible, drawer closed and composer on screen', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/app', { waitUntil: 'domcontentloaded' });

  const state = await page.evaluate(() => {
    const side = document.querySelector('.inspiration-side');
    const composer = document.querySelector('.inspiration-composer');
    const rect = composer.getBoundingClientRect();
    const launcher = document.querySelector('.facai-tools-launcher');
    return {
      drawerOpen: side.classList.contains('is-open'),
      composerTop: rect.top,
      composerBottom: rect.bottom,
      viewportHeight: window.innerHeight,
      launcherHidden: launcher && getComputedStyle(launcher).display === 'none',
      mobileUtilityCount: document.querySelectorAll('.nav-mobile-utility').length,
    };
  });

  expect(state.drawerOpen).toBe(false);
  expect(state.composerTop).toBeGreaterThanOrEqual(0);
  expect(state.composerBottom).toBeLessThanOrEqual(state.viewportHeight + 1);
  expect(state.launcherHidden).toBe(true);
  expect(state.mobileUtilityCount).toBe(4);

  await page.locator('#historyDrawerToggle').click();
  await expect(page.locator('.inspiration-side')).toHaveClass(/is-open/);
  await expect(page.locator('#historyDrawerBackdrop')).toHaveClass(/is-open/);
});

test('tools launcher is one accessible disclosure and filters the current tool', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });

  for (const path of TOOL_PAGES) {
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.facai-tools-launcher'), `${path} should render tools`).toHaveCount(1);
    await expect(page.locator('#facaiToolsToggle'), `${path} tools should be visible`).toBeVisible();
  }

  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });

  await expect(page.locator('.facai-tools-launcher')).toHaveCount(1);
  const toggle = page.locator('#facaiToolsToggle');
  const menu = page.locator('#facaiToolsMenu');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(menu).toBeVisible();
  await expect(menu.locator('a')).toHaveCount(3);
  await expect(page.locator('body')).toHaveClass(/facai-tools-open/);

  await page.keyboard.press('Escape');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(toggle).toBeFocused();

  await toggle.click();
  await page.locator('main').click({ position: { x: 5, y: 5 } });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');

  await page.goto('/app/import', { waitUntil: 'domcontentloaded' });
  await page.locator('#facaiToolsToggle').click();
  await expect(page.locator('#facaiToolsMenu a')).toHaveCount(2);
  await expect(page.locator('#facaiToolsMenu a[href="/app/import"]')).toHaveCount(0);
});

test('generate scroll top stays clear of tools and hides while disclosure is open', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(100);

  const positions = await page.evaluate(() => {
    const scroll = document.querySelector('.scroll-top-btn').getBoundingClientRect();
    const launcher = document.querySelector('.facai-tools-launcher').getBoundingClientRect();
    return { scrollBottom: scroll.bottom, launcherTop: launcher.top };
  });
  expect(positions.scrollBottom).toBeLessThanOrEqual(positions.launcherTop);

  await page.locator('#facaiToolsToggle').click();
  await expect(page.locator('.scroll-top-btn')).toHaveCSS('visibility', 'hidden');
});

test('generate workspace survives module navigation and reload in the same tab', async ({ page, context }) => {
  await mockGenerateWorkspaceApis(page);
  await page.setViewportSize({ width: 1280, height: 760 });
  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.product-card')).toHaveCount(1);

  await page.locator('.product-card').click();
  await page.locator('#productDetailNext').click();
  await page.locator('.type-tag').filter({ hasText: '成本低' }).click();
  await page.locator('#aiEngine').selectOption('deepseek');
  await page.locator('#includeShotDesign').check();
  await page.locator('#reqPreFill').fill('突出门店赶单时的稳定性');
  await page.locator('#btnGenerate').click();

  await expect(page.locator('#scriptOutput')).toContainText('初始生成脚本');
  await expect(page.locator('#contentBreakdownList')).toContainText('先指出赶单时的稳定性问题');
  const editedScript = ['用户编辑后的脚本', ...Array(80).fill('冷藏稳定，赶单也能保持出品效果。')].join('\n');
  await page.locator('#scriptOutput').fill(editedScript);
  await page.locator('#optimizeInput').fill('开头先展示失败场景');
  await page.locator('#templateReferenceDetails').evaluate(element => { element.open = true; });
  await page.evaluate(() => {
    document.querySelector('#scriptOutput').scrollTop = 240;
    document.querySelector('.breakdown-panel').scrollTop = 180;
    window.scrollTo(0, 160);
  });
  await page.waitForTimeout(250);

  await page.locator('.nav-links a[href="/app/products"]').click();
  await page.locator('.nav-links a[href="/app/generate"]').click();
  await expect(page.locator('#step3')).toBeVisible();
  await expect(page.locator('#scriptOutput')).toContainText('用户编辑后的脚本');
  await expect(page.locator('#optimizeInput')).toHaveValue('开头先展示失败场景');
  await expect(page.locator('#reqPreFill')).toHaveValue('突出门店赶单时的稳定性');
  await expect(page.locator('#aiEngine')).toHaveValue('deepseek');
  await expect(page.locator('#includeShotDesign')).toBeChecked();
  await expect(page.locator('#contentBreakdownList')).toContainText('先指出赶单时的稳定性问题');
  await expect(page.locator('#breakdownStale')).toBeVisible();
  await expect(page.locator('#templateReferenceDetails')).toHaveAttribute('open', '');
  await expect.poll(() => page.locator('#scriptOutput').evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await expect.poll(() => page.locator('.breakdown-panel').evaluate(element => element.scrollTop)).toBeGreaterThan(0);

  await page.reload({ waitUntil: 'domcontentloaded' });
  await expect(page.locator('#step3')).toBeVisible();
  await expect(page.locator('#scriptOutput')).toContainText('用户编辑后的脚本');
  await expect(page.locator('#optimizeInput')).toHaveValue('开头先展示失败场景');

  const freshPage = await context.newPage();
  await mockGenerateWorkspaceApis(freshPage);
  await freshPage.goto('/app/generate', { waitUntil: 'domcontentloaded' });
  await expect(freshPage.locator('#step1')).toBeVisible();
  expect(await freshPage.evaluate(() => sessionStorage.getItem('facai.generate.workspace.v1'))).toBeNull();
  await freshPage.close();
});

test('generate workspace resumes an active job and discards malformed snapshots', async ({ page }) => {
  await mockGenerateWorkspaceApis(page, { runningFirst: true });
  await page.goto('/app/products', { waitUntil: 'domcontentloaded' });
  await page.evaluate(product => {
    sessionStorage.setItem('facai.generate.workspace.v1', JSON.stringify({
      version: 1,
      step: 3,
      selection: { product, video_type: '成本低', category: '', search: '' },
      settings: { engine: 'deepseek', include_shot_design: false, requirements: '' },
      result: { script_id: null, script_content: '', info: null, template_reference: null, breakdown: null, breakdown_stale: false },
      optimize_input: '',
      active_job_id: 'workspace-job',
      generating: true,
      scroll: {},
    }));
  }, WORKSPACE_PRODUCT);
  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#generatingHint')).toBeVisible();
  await expect(page.locator('#scriptOutput')).toContainText('初始生成脚本', { timeout: 5000 });

  await page.goto('/app/products', { waitUntil: 'domcontentloaded' });
  await page.evaluate(() => sessionStorage.setItem('facai.generate.workspace.v1', '{broken-json'));
  await page.goto('/app/generate', { waitUntil: 'domcontentloaded' });
  await expect(page.locator('#step1')).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem('facai.generate.workspace.v1'))).toBeNull();
});

test('desktop AI work keeps the two-column layout', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto('/app', { waitUntil: 'domcontentloaded' });

  const columns = await page.locator('.inspiration-shell').evaluate(
    element => getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length,
  );
  await expect(page.locator('.inspiration-side')).toBeVisible();
  await expect(page.locator('.inspiration-composer')).toBeVisible();
  expect(columns).toBe(2);
});

test('API connections opens directly without a login session', async ({ page }) => {
  await page.goto('/app/api-connections', { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('heading', { name: '电商 API 接入中心' })).toBeVisible();
  await expect(page.locator('.provider-connection-row')).toHaveCount(4);
  await expect(page.locator('#integrationLogout')).toHaveCount(0);
  await expect(page.getByText('功能框架已就绪，连接器尚未配置')).toBeVisible();
  await expect(page.locator('#facaiToolsToggle')).toBeVisible();
});

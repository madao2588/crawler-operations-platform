import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const testDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(testDirectory, '..', '..');
const packagePath = path.join(repositoryRoot, 'package.json');
const workspacePackagePath = path.resolve(repositoryRoot, '..', 'package.json');
const devUpPath = path.join(repositoryRoot, 'scripts', 'dev-up.ps1');
const pythonWrapperPath = path.join(repositoryRoot, 'scripts', 'pythonw.ps1');
const composePath = path.join(repositoryRoot, 'docker-compose.yml');
test('npm start launches React and keeps explicit Flutter rollback commands', () => {
  assert.equal(existsSync(packagePath), true, 'root package.json must exist');

  const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'));
  assert.equal(packageJson.private, true);
  assert.equal(
    packageJson.scripts?.start,
    'powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/dev-up.ps1',
  );
  assert.equal(
    packageJson.scripts?.stop,
    'powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/dev-down.ps1',
  );
  assert.equal(
    packageJson.scripts?.['start:react'],
    'powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/dev-up.ps1 -FrontendMode react',
  );
  assert.equal(
    packageJson.scripts?.['start:flutter'],
    'powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/dev-up.ps1 -FrontendMode flutter',
  );
  assert.equal(
    packageJson.scripts?.['stop:flutter'],
    'powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/dev-down.ps1',
  );
});

test('combined launcher supports React mode directly', () => {
  const launcher = readFileSync(devUpPath, 'utf8');

  assert.match(launcher, /\[string\]\$FrontendMode = 'react'/);
  assert.match(launcher, /Supported values: flutter, react/);
  assert.match(launcher, /\$useReactFrontend = \$FrontendMode\.ToLowerInvariant\(\) -eq "react"/);
  assert.match(launcher, /npm run dev -- --host 0\.0\.0\.0 --port \$FrontendPort/);
  assert.match(launcher, /uvicorn main:app/);
  assert.match(launcher, /uvicorn main:app --host 127\.0\.0\.1/);
  assert.match(launcher, /Wait-ForHttpOk -Url "http:\/\/127\.0\.0\.1:\$BackendPort\/health"/);
  assert.match(launcher, /Wait-ForHttpOk -Url "http:\/\/127\.0\.0\.1:\$FrontendPort\/"/);
  assert.match(launcher, /LAN URL:/);
});

test('combined launcher waits for backend health before exposing the frontend', () => {
  const launcher = readFileSync(devUpPath, 'utf8');
  const backendHealthWait = launcher.indexOf(
    'Wait-ForHttpOk -Url "http://127.0.0.1:$BackendPort/health"',
  );
  const frontendStart = launcher.indexOf(
    'Write-Host "Starting frontend ($FrontendMode) on http://127.0.0.1:$FrontendPort ..."',
  );

  assert.notEqual(backendHealthWait, -1, 'backend health wait must exist');
  assert.notEqual(frontendStart, -1, 'frontend startup must exist');
  assert.ok(
    backendHealthWait < frontendStart,
    'frontend must not start until the backend health endpoint is ready',
  );
});

test('workspace root npm start delegates to crawler_system', () => {
  assert.equal(
    existsSync(workspacePackagePath),
    true,
    'workspace root package.json must exist',
  );

  const packageJson = JSON.parse(readFileSync(workspacePackagePath, 'utf8'));
  assert.equal(packageJson.private, true);
  assert.equal(packageJson.scripts?.start, 'npm --prefix ./crawler_system start');
  assert.equal(packageJson.scripts?.stop, 'npm --prefix ./crawler_system stop');
  assert.equal(
    packageJson.scripts?.['start:flutter'],
    'npm --prefix ./crawler_system run start:flutter',
  );
  assert.equal(
    packageJson.scripts?.['stop:flutter'],
    'npm --prefix ./crawler_system run stop:flutter',
  );
});

test('combined launcher avoids misleading admin and transient log warnings', () => {
  const launcher = readFileSync(devUpPath, 'utf8');

  assert.doesNotMatch(launcher, /Bootstrap admin is not configured/);
  assert.match(launcher, /\$LogFileClearAttempts\s*=\s*20/);
  assert.match(launcher, /Start-Sleep -Milliseconds 150/);
});

test('combined launcher serves a stable release build instead of the DDC debug server', () => {
  const launcher = readFileSync(devUpPath, 'utf8');

  assert.match(launcher, /frontend-build\.ps1/);
  assert.match(launcher, /build\\web/);
  assert.match(launcher, /-m http\.server/);
  assert.match(launcher, /npm run dev -- --host 0\.0\.0\.0 --port \$FrontendPort/);
  assert.doesNotMatch(launcher, /run -d web-server/);
  assert.match(
    launcher,
    /Wait-ForHttpOk -Url "http:\/\/127\.0\.0\.1:\$FrontendPort\/"/,
  );
});

test('dev-check validates both React primary flow and Flutter fallback', () => {
  const devCheckPath = path.join(repositoryRoot, 'scripts', 'dev-check.ps1');
  const checker = readFileSync(devCheckPath, 'utf8');

  assert.match(checker, /Running React frontend typecheck/);
  assert.match(checker, /npm\.cmd --prefix \$reactFrontendDir run typecheck/);
  assert.match(checker, /npm\.cmd --prefix \$reactFrontendDir test/);
  assert.match(checker, /npm\.cmd --prefix \$reactFrontendDir run build/);
  assert.match(checker, /Running Flutter frontend analyze/);
  assert.match(checker, /Running Flutter frontend tests/);
});

test('combined launcher cleans up partial startup and prints useful log tails', () => {
  const launcher = readFileSync(devUpPath, 'utf8');

  assert.match(launcher, /function Stop-LaunchedProcess/);
  assert.match(launcher, /taskkill \/PID \$Process\.Id \/T \/F/);
  assert.match(launcher, /function Write-LogTail/);
  assert.match(launcher, /Get-Content -LiteralPath \$Path -Tail/);
  assert.match(launcher, /catch\s*\{/);
  assert.match(launcher, /Stop-PortProcesses -Port \$BackendPort/);
  assert.match(launcher, /Stop-PortProcesses -Port \$FrontendPort/);
});

test('deployment passes outbound network settings to the backend container', () => {
  const compose = readFileSync(composePath, 'utf8');

  assert.match(compose, /http:\/\/127\.0\.0\.1:8093/);
  assert.match(compose, /CRAWLER_OUTBOUND_PROXY_URL:/);
  assert.match(compose, /CRAWLER_USE_SYSTEM_PROXY:/);
  assert.match(compose, /CRAWLER_OUTBOUND_NO_PROXY:/);
});

test('python wrapper forces UTF-8 output for Chinese Windows acceptance checks', () => {
  const wrapper = readFileSync(pythonWrapperPath, 'utf8');

  assert.match(wrapper, /\$env:PYTHONIOENCODING\s*=\s*["']utf-8["']/i);
  assert.match(wrapper, /\$env:PYTHONUTF8\s*=\s*["']1["']/i);
});

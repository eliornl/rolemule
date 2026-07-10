/**
 * CV Optimizer tab entry — called from application-detail when Optimize tab opens.
 */
import { attachEventListeners } from '../cv-optimizer/listeners';
import { loadCvOptimizationStatus } from '../cv-optimizer/load';
import { checkApiKeyStatus } from '../cv-optimizer/setup';
import { attachWsListener } from '../cv-optimizer/websocket';
import { setSessionId } from '../cv-optimizer/state-access';

export function initCvOptimizerTab(sessionId: string | null): void {
  setSessionId(sessionId);
  if (!sessionId) return;
  attachEventListeners();
  attachWsListener();
  void checkApiKeyStatus();
  void loadCvOptimizationStatus();
}

window.initCvOptimizerTab = initCvOptimizerTab;

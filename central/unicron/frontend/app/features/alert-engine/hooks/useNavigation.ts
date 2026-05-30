import { useState } from 'react';

export type TabType = 'dashboard' | 'alerts' | 'rules' | 'containers';

export function useNavigation() {
  const [activeTab, setActiveTab] = useState<TabType>('dashboard');
  return { activeTab, setActiveTab };
}

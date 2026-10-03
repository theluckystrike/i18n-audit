import { useTranslation, Trans } from 'react-i18next';
import i18n from 'i18next';

export function App({ section }: { section: string }) {
  const { t } = useTranslation('common');
  const title = t('nested.deep.title', { workspace: 'w' });
  const greet = t("greeting", { name: 'x' });
  const missing = t('dashboard.emptyState');
  const dynamic = t(`sections.${section}`);
  const plural = t('items', { count: 3 });
  const other = i18n.t('auth:login');
  const absentNs = i18n.t('auth:signup');
  const obj = t('nested.deep', { returnObjects: true });
  return <Trans i18nKey="terms" t={t} />;
}

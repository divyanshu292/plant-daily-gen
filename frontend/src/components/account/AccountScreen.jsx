import { useEffect, useState } from 'react';
import { ArrowClockwiseIcon, CheckIcon, CircleNotchIcon, LockSimpleIcon, SignOutIcon } from '@phosphor-icons/react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Notice } from '@/components/common/Notice';
import { PageHeading, SectionTitle } from '@/components/common/Text';
import { ACCESS_TEXT, ActivityList, Field, INPUT_CLASS, INVALID_CLASS, PasswordInput, RoleBadge } from '@/components/account/AccountParts';
import { api } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useApiData } from '@/lib/hooks';
import { cn } from '@/lib/utils';

/** The signed-in person's own page: name, password, what they have done, sign out. Every role. */
export function AccountScreen() {
  const { user, setUser, logout } = useAuth();
  if (!user) return null;
  return <Account user={user} setUser={setUser} logout={logout} />;
}

function Account({ user, setUser, logout }) {
  const activity = useApiData('/auth/activity?limit=100');

  return (
    <div className="max-w-2xl space-y-10 lg:max-w-none">
      <PageHeading
        eyebrow="Account"
        title={<span className="break-words">{user.name}</span>}
        subtitle={
          <>
            <RoleBadge role={user.role} className="mr-2 align-[1px]" />
            {ACCESS_TEXT[user.role]}
          </>
        }
      />

      {/* Phones: profile, password, activity, sign out. Wide screens: activity in its own column. */}
      <div className="grid gap-10 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)] lg:grid-rows-[auto_1fr] lg:gap-x-12">
        <div className="space-y-10 lg:col-start-1 lg:row-start-1">
          <section className="space-y-3">
            <SectionTitle title="Profile" />
            <Card className="divide-y divide-border">
              <div className="px-4 py-4 md:px-5">
                <NameForm user={user} setUser={setUser} onSaved={activity.reload} />
              </div>
              <div className="space-y-1 px-4 py-4 md:px-5">
                <div className="text-sm font-medium">Email</div>
                <div className="flex min-w-0 items-center gap-2 text-sm">
                  <LockSimpleIcon weight="fill" className="h-3.5 w-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  <span className="break-all">{user.email}</span>
                </div>
                <p className="text-xs text-muted-foreground">You sign in with this. It can&apos;t be changed.</p>
              </div>
            </Card>
          </section>

          <section className="space-y-3">
            <SectionTitle title="Password" hint="Changing it signs you out on your other devices." />
            <Card className="px-4 py-4 md:px-5">
              <PasswordForm email={user.email} onChanged={activity.reload} />
            </Card>
          </section>
        </div>

        <section className="space-y-3 lg:col-start-2 lg:row-span-2 lg:row-start-1">
          <SectionTitle title="Activity" hint="What you have done here, newest first. Times are IST.">
            {activity.loading && activity.data && (
              <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin text-muted-foreground" />
            )}
          </SectionTitle>
          {activity.error && (
            <Notice
              tone="error"
              title="Could not load your activity"
              action={
                <Button variant="outline" size="touch" onClick={activity.reload}>
                  <ArrowClockwiseIcon weight="bold" />
                  Try again
                </Button>
              }
            >
              {activity.error.message}
            </Notice>
          )}
          {!activity.data && activity.loading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <CircleNotchIcon weight="bold" className="h-4 w-4 animate-spin" /> Loading
            </div>
          )}
          {activity.data && (
            <Card className="px-4 py-2 md:px-5">
              <ActivityList items={activity.data} />
            </Card>
          )}
        </section>

        <div className="lg:col-start-1 lg:row-start-2 lg:self-start">
          <SignOut logout={logout} />
        </div>
      </div>
    </div>
  );
}

function NameForm({ user, setUser, onSaved }) {
  const [draft, setDraft] = useState(user.name);
  const [state, setState] = useState({ status: 'idle' }); // idle | saving | saved | error
  useEffect(() => setDraft(user.name), [user.name]);

  const name = draft.trim();
  const changed = name !== user.name;
  const saving = state.status === 'saving';

  const save = async (e) => {
    e.preventDefault();
    if (!name) {
      setState({ status: 'error', error: 'Enter your name.' });
      return;
    }
    if (!changed || saving) return;
    setState({ status: 'saving' });
    try {
      const res = await api('/auth/me', { method: 'PATCH', json: { name } });
      setUser(res.user);
      setState({ status: 'saved' });
      onSaved?.();
    } catch (err) {
      setState({ status: 'error', error: err.message });
    }
  };

  return (
    <form onSubmit={save} noValidate>
      <Field id="account-name" label="Name" error={state.status === 'error' ? state.error : null}>
        <div className="flex gap-2">
          <input
            id="account-name"
            type="text"
            value={draft}
            maxLength={80}
            autoComplete="name"
            enterKeyHint="done"
            aria-invalid={state.status === 'error' || undefined}
            aria-describedby="account-name-note"
            onChange={(e) => {
              setDraft(e.target.value);
              if (!saving) setState({ status: 'idle' });
            }}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setDraft(user.name);
                setState({ status: 'idle' });
              }
            }}
            className={cn(INPUT_CLASS, state.status === 'error' && INVALID_CLASS)}
          />
          <Button type="submit" size="touch" className="min-w-[5.5rem] shrink-0 md:h-10" disabled={!changed || !name || saving}>
            {saving ? (
              <CircleNotchIcon weight="bold" className="animate-spin" />
            ) : state.status === 'saved' && !changed ? (
              <CheckIcon weight="bold" />
            ) : null}
            {saving ? 'Saving' : state.status === 'saved' && !changed ? 'Saved' : 'Save'}
          </Button>
        </div>
      </Field>
    </form>
  );
}

const EMPTY_PASSWORDS = { current: '', next: '', confirm: '' };

function PasswordForm({ email, onChanged }) {
  const [values, setValues] = useState(EMPTY_PASSWORDS);
  const [errors, setErrors] = useState({});
  const [state, setState] = useState({ status: 'idle' }); // idle | saving | done | error
  const saving = state.status === 'saving';

  const set = (key) => (e) => {
    const v = e.target.value;
    setValues((s) => ({ ...s, [key]: v }));
    setErrors((s) => ({ ...s, [key]: null }));
    if (state.status !== 'saving') setState({ status: 'idle' });
  };

  const submit = async (e) => {
    e.preventDefault();
    if (saving) return;
    const errs = {};
    if (!values.current) errs.current = 'Enter your current password.';
    if (values.next.length < 8) errs.next = 'Use at least 8 characters.';
    else if (values.next.length > 128) errs.next = 'Use 128 characters or fewer.';
    else if (values.confirm !== values.next) errs.confirm = 'This does not match the new password.';
    setErrors(errs);
    if (Object.keys(errs).some((k) => errs[k])) return;

    setState({ status: 'saving' });
    try {
      await api('/auth/password', {
        method: 'POST',
        json: { currentPassword: values.current, newPassword: values.next },
      });
      setValues(EMPTY_PASSWORDS);
      setState({ status: 'done' });
      onChanged?.();
    } catch (err) {
      setState({ status: 'error', error: err.message });
    }
  };

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      {/* Lets password managers tie the new password to this account. */}
      <input type="text" name="username" autoComplete="username" value={email} readOnly hidden />
      <Field id="pw-current" label="Current password" error={errors.current}>
        <PasswordInput
          id="pw-current"
          value={values.current}
          onChange={set('current')}
          autoComplete="current-password"
          invalid={!!errors.current}
        />
      </Field>
      <Field id="pw-next" label="New password" error={errors.next} hint="At least 8 characters.">
        <PasswordInput id="pw-next" value={values.next} onChange={set('next')} autoComplete="new-password" invalid={!!errors.next} />
      </Field>
      <Field id="pw-confirm" label="Confirm new password" error={errors.confirm}>
        <PasswordInput
          id="pw-confirm"
          value={values.confirm}
          onChange={set('confirm')}
          autoComplete="new-password"
          enterKeyHint="done"
          invalid={!!errors.confirm}
        />
      </Field>

      {state.status === 'done' && <Notice tone="success" title="Password changed. Other devices were signed out." />}
      {state.status === 'error' && (
        <Notice tone="error" title="Password not changed">
          {state.error}
        </Notice>
      )}

      <Button type="submit" size="touch" className="w-full sm:w-auto" disabled={saving}>
        {saving && <CircleNotchIcon weight="bold" className="animate-spin" />}
        {saving ? 'Changing' : 'Change password'}
      </Button>
    </form>
  );
}

function SignOut({ logout }) {
  const [state, setState] = useState({ status: 'idle' }); // idle | busy | error
  const signOut = async () => {
    setState({ status: 'busy' });
    try {
      await logout();
    } catch (err) {
      // Only the server can clear the session cookie, so a failed call leaves the person signed in.
      setState({ status: 'error', error: err?.message || 'Could not sign out.' });
      return;
    }
    setState({ status: 'idle' });
  };
  return (
    <div className="space-y-3">
      {state.status === 'error' && (
        <Notice tone="error" title="Still signed in">
          {state.error}
        </Notice>
      )}
      <Button variant="outline" size="touch" className="w-full sm:w-auto" onClick={signOut} disabled={state.status === 'busy'}>
        {state.status === 'busy' ? <CircleNotchIcon weight="bold" className="animate-spin" /> : <SignOutIcon weight="bold" />}
        Sign out
      </Button>
    </div>
  );
}

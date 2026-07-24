import { useAuth } from "./auth";
import { Login } from "./components/Login";
import { Dashboard } from "./components/Dashboard";
import { Spinner } from "./ui";

export function App() {
  const { identity, loading } = useAuth();
  if (loading) {
    return (
      <div className="splash">
        <Spinner />
      </div>
    );
  }
  return identity ? <Dashboard /> : <Login />;
}

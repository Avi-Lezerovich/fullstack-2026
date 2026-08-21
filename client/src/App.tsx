import Box from "@mui/material/Box";
import Container from "@mui/material/Container";
import { Navigate, Route, Routes } from "react-router-dom";

import Footer from "./components/layout/Footer";
import TopBar from "./components/layout/TopBar";
import ProtectedRoute from "./components/routing/ProtectedRoute";
import AdminDashboard from "./pages/AdminDashboard";
import CasePage from "./pages/CasePage";
import Feed from "./pages/Feed";
import ForgotPassword from "./pages/ForgotPassword";
import Login from "./pages/Login";
import Messages from "./pages/Messages";
import NewCase from "./pages/NewCase";
import Profile from "./pages/Profile";
import ResetPassword from "./pages/ResetPassword";
import Signup from "./pages/Signup";
import Users from "./pages/Users";

const App = () => {
  return (
    <Box sx={{ display: "flex", flexDirection: "column", minHeight: "100vh" }}>
      <TopBar />

      <Box component="main" sx={{ flex: 1 }}>
        <Container maxWidth="md" sx={{ py: 3 }}>
          <Routes>
            <Route path="/" element={<Feed />} />
            <Route path="/cases/new" element={<ProtectedRoute><NewCase /></ProtectedRoute>} />
            <Route path="/cases/:caseId" element={<CasePage />} />
            <Route path="/users" element={<Users />} />
            <Route
              path="/messages"
              element={<ProtectedRoute><Messages /></ProtectedRoute>}
            />
            <Route path="/users/:userId" element={<Profile />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route
              path="/admin"
              element={<ProtectedRoute><AdminDashboard /></ProtectedRoute>}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Container>
      </Box>

      <Footer />
    </Box>
  );
}; export default App;

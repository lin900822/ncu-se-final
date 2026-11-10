import { BrowserRouter, Route, Routes } from 'react-router-dom'
import Home from './pages/Home'
import StudentJoin from './pages/StudentJoin'
import TeacherRoom from './pages/TeacherRoom'

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-slate-50 text-slate-900">
        <div className="mx-auto max-w-3xl px-4 py-8">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/teacher" element={<TeacherRoom />} />
            <Route path="/join" element={<StudentJoin />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}

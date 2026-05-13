import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Form, Input, Button, Card, Typography, message, Space } from 'antd';
import { UserOutlined, LockOutlined, GlobalOutlined } from '@ant-design/icons';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { loginThunk, clearError } from '@/store/slices/authSlice';
const { Title, Text } = Typography;
export default function LoginPage() {
    const [loading, setLoading] = useState(false);
    const dispatch = useAppDispatch();
    const navigate = useNavigate();
    const { token, error } = useAppSelector((state) => state.auth);
    useEffect(() => {
        if (token) {
            navigate('/', { replace: true });
        }
    }, [token, navigate]);
    useEffect(() => {
        if (error) {
            message.error(error);
            dispatch(clearError());
        }
    }, [error, dispatch]);
    const onFinish = async (values) => {
        setLoading(true);
        try {
            await dispatch(loginThunk(values)).unwrap();
            message.success('登录成功');
            navigate('/', { replace: true });
        }
        catch {
            // error handled in useEffect
        }
        finally {
            setLoading(false);
        }
    };
    return (React.createElement("div", { style: {
            minHeight: '100vh',
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        } },
        React.createElement(Card, { style: { width: 400, boxShadow: '0 8px 24px rgba(0,0,0,0.15)' } },
            React.createElement("div", { style: { textAlign: 'center', marginBottom: 32 } },
                React.createElement(Space, null,
                    React.createElement(GlobalOutlined, { style: { fontSize: 32, color: '#667eea' } }),
                    React.createElement(Title, { level: 3, style: { margin: 0 } }, "\u6D77\u5916\u4E2D\u56FD\u6587\u7269\u77E5\u8BC6\u56FE\u8C31")),
                React.createElement("div", { style: { marginTop: 8 } },
                    React.createElement(Text, { type: "secondary" }, "\u8BF7\u767B\u5F55\u4EE5\u7EE7\u7EED"))),
            React.createElement(Form, { name: "login", onFinish: onFinish, size: "large", autoComplete: "off" },
                React.createElement(Form.Item, { name: "username", rules: [{ required: true, message: '请输入用户名' }] },
                    React.createElement(Input, { prefix: React.createElement(UserOutlined, null), placeholder: "\u7528\u6237\u540D" })),
                React.createElement(Form.Item, { name: "password", rules: [{ required: true, message: '请输入密码' }] },
                    React.createElement(Input.Password, { prefix: React.createElement(LockOutlined, null), placeholder: "\u5BC6\u7801" })),
                React.createElement(Form.Item, null,
                    React.createElement(Button, { type: "primary", htmlType: "submit", loading: loading, block: true }, "\u767B\u5F55"))))));
}

import { Component } from "react";

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed) {
      return <p className="muted">{this.props.fallback || "This part could not be shown. The list below still works."}</p>;
    }
    return this.props.children;
  }
}
